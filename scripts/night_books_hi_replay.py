"""BOOKS H and I — the first read of two tables this repository has never joined.

WHY THIS JOB EXISTS
===================
CLAUDE.md's bottleneck diagnosis is that all ten arena books select on ONE
signal and differ in portfolio treatment, not in alpha source. The 2026-09-13
round-3 spec found two mechanisms that need NO collector at all, only a read of
files already on disk:

  H  option_grant_timing_v0          TRIAL-DRAFT-H   `trans_code == 'A'`,
                                     `table == 'DERIV'` — the derivative GRANT
                                     AWARD rows `scripts/sec_insider_bulk_load.py`
                                     DISCARDS when it distils
                                     `insider_events_v1.parquet` down to
                                     open-market purchases and sales. 1,276,210
                                     of them, unread since the August pull.
  I  buyback_insider_divergence_v0   TRIAL-DRAFT-I   `comp__funda.prstkc`
                                     (repurchases) joined through `link_ccm` to
                                     `trans_code == 'S'` Form-4 SALES. Two
                                     tables both already here; nobody had ever
                                     put them on the same row.

THE SAME ENGINE, ON PURPOSE
===========================
Every leg runs through `night_first_books_replay.run_monthly` — the same twin,
the same flat 25 bps ruler, the same Newey-West lag-2 t, the same `by_era`
split — that Books A/C and then E/F/G were read under. A new book that brought
its own engine would be a comparison of two engines wearing the names of two
books.

WHAT IS NEW IS `pool_filter`, AND IT IS THE POINT
=================================================
Both books require something of a name that the market does not require of
every name: a grant history, or a repurchase line plus Form-4 coverage. A book
measured against a twin drawn from names that require NEITHER is measuring
coverage and calling it selection. `run_monthly(pool_filter=...)` narrows the
eligible band BEFORE either leg sees it.

BOOK I IS QUARTERLY, AND THE ENGINE IS UNMODIFIED
=================================================
`prstkc` is an ANNUAL Compustat field — `compustat_fundq.parquet` carries no
repurchase column at all, verified — so a monthly rebalance would charge four
rebalances' costs for one refresh of information. The monthly panel is
PRE-AGGREGATED into quarterly `ym` buckets and the same `run_monthly` is run
over those. The alternative (a `rebalance_months` gate inside the engine) would
change the code five other books were read under. The receipt says which was
done, because "quarterly" and "monthly on a stale score" are different books.

BOTH FLOORS IN ONE PASS, TWIN RE-DRAWN AT EACH
==============================================
TRIAL-H5's lesson and `A_corner`'s: a corner-dependent control must be
RE-MEASURED at every corner. `floor_usd` moves the book, the twin and the
falsifier universes together, and every book here is read at the $3M primary
and the $10M secondary floor in one job so that neither can be quoted alone.

THE RECEIPT PRINTS THE CONSTRUCTION
===================================
Book C's 2026-09-13 lesson: run 1 warmed a 60-month overhang at 24 months and
the receipt said `confirm_slice 1995-2024` anyway. Every cell here carries
`registered_construction` with the frozen parameters it actually used and a
boolean `honours_the_registration`, so a smoke window cannot be mistaken for
the registered read.

    python -m scripts.night_factory_jobs B_books_hi_replay --smoke
    NIGHT_RUN_DATE=2026-09-14 python -m scripts.night_factory_jobs B_books_hi_replay

TIME: Book H reads nineteen years of CRSP DAILY to build its grant windows and
then expands ~70k (issuer, insider) pairs across ~228 months; Book I reads the
941k-row `funda` and the 82-file Form-4 tape. Projection 20-60 minutes on CPU.
Queue it with an explicit box — a job killed at its time limit writes no
receipt at all (2026-09-10, G3 at generation 340).
"""

from __future__ import annotations

import gc
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

from scripts.night_books_efg_replay import (
    CharacteristicPanelUnavailable,
    T_ALIVE,
    _big_half_filter,
    _pool_filter,
    era_stability,
)
from scripts.night_first_books_replay import (
    COST_BPS_PER_SIDE,
    COST_CURVE,
    ERAS,
    FLOOR_USD as REPLAY_FLOOR_USD,
    by_era,
    eligible,
    holm,
    load_monthly_panel,
    run_monthly,
    wrds_dir,
)

logger = logging.getLogger("books_hi_replay")

JOB = "B_books_hi_replay"

#: THE THIRD FAMILY, DECLARED AT SIZE TWO BEFORE EITHER READ. It does not extend
#: `NIGHT_JOB_BOOKS_2026_09_13` (E, F, G, C_v1) or `NIGHT_JOB_BOOKS_2026_09`
#: (A, B, C, D); both of those have read their primaries and spent their
#: budgets, and a family that grows after its numbers are seen is a family
#: fitted to a result.
FAMILY = "NIGHT_JOB_BOOKS_2026_09_14"
DECLARED_FAMILY = ("option_grant_timing_v0", "buyback_insider_divergence_v0")

#: Frozen by both registrations.
K = 30
TERCILE = 2.0 / 3.0
PRIMARY_FLOOR_USD = None                      # the replay's own $3M
SECONDARY_FLOOR_USD = 10_000_000.0

SEEDS = {"H": 0x0848, "I": 0x0949}

#: Each draft's section 4. **H is per MONTH and I is per QUARTER** — the unit is
#: the one the book earns, and mixing them is the error that made TRIAL-DRAFT-I's
#: first draft come back UNPOWERED_AT_REGISTRATION from the linter.
DECLARED_EFFECT = {"H": 0.0065, "I": 0.0150}
DECLARED_UNIT = {"H": "month", "I": "quarter"}
#: (nominal, autocorrelation-deflated) MDE, from each draft's own section 4.
DECLARED_MDE = {"H": (0.00901, 0.01023), "I": (0.02502, 0.02852)}
MDE_Z_SUM = 2.8                               # 1.96 + 0.84, two-sided, 80% power

#: The read window. Form-4 coverage begins 2006q1 and CRSP daily ends 2024.
FULL_START, FULL_END = 2006, 2024

#: The smoke window. Seven recent years and the 400 largest names by median
#: dollar volume: enough for a grant history to exist and for a tercile not to
#: be a cut of six names, and short enough to prove the job runs.
SMOKE_START, SMOKE_END, SMOKE_NAMES = 2018, 2024, 400

#: Both registrations' contamination clause, verbatim: exclude a year whose
#: covered share inside the eligible band falls below 0.10, OR whose MEDIAN
#: block carries fewer than 3k covered names.
MIN_COVERAGE_SHARE = 0.10
MIN_COVERED_NAMES_MEDIAN = 3 * K

# -- Book H's frozen inputs (TRIAL-DRAFT-H section 6) ----------------------
GRANT_WINDOW = 20                 # trading sessions, [-20,-1] and [+1,+20]
GRANT_RECENCY_MONTHS = 36         # the pool filter's own recency requirement
PLACEBO_OFFSET_DAYS = (90, 180)   # the registered random-date placebo band
PLACEBO_SEED = 0x504C
#: A guard, not a parameter. The pair-month expansion is the one step in this
#: job that can silently eat the machine, and a refusal by name beats an OOM at
#: 03:00 that writes no receipt.
MAX_PAIR_MONTHS = 40_000_000
#: Larger than any session index a two-decade window can produce, so that
#: `permno * BASE + session` sorts exactly the way `(permno, session)` does.
SESSION_KEY_BASE = 1 << 20

# -- Book I's frozen inputs (TRIAL-DRAFT-I section 6) ----------------------
BUYBACK_RECENCY_MONTHS = 18
BUYBACK_FALLBACK_DAYS = 180       # measured: pdate lag q90 is already 125 days
SALE_WINDOW_DAYS = 90
FORM4_COVERAGE_DAYS = 365
LARGE_SALE_SHARE = 0.10           # the FAJ 2004 cut, a REPORTED diagnostic
FUNDA_FILTER = {"indfmt": "INDL", "datafmt": "STD", "popsrc": "D",
                "consol": "C", "curcd": "USD"}
FUNDA_COLUMNS = ("gvkey", "datadate", "indfmt", "datafmt", "popsrc", "consol",
                 "curcd", "prstkc", "csho", "prcc_f", "pdate", "fdate")
LINK_COLUMNS = ("gvkey", "permno", "linktype", "linkprim", "linkdt",
                "linkenddt")
LINK_TYPES = ("LU", "LC")
LINK_PRIMS = ("P", "C")
INSIDER_COLUMNS = ("permno", "issuer_cik", "owner_cik", "table", "trans_code",
                   "acquired_disposed", "shares", "shares_owned_following",
                   "trans_date", "filing_date", "plan_10b5_1")


def insider_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "sec_insider" / "parsed"


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "first_books" / "replay"


# --------------------------------------------------------------------------
# shared statistics (local copies, and the reason they are local)
#
# `night_books_efg_replay`'s `run_cell`, `decide_cell` and `recompute_mde` read
# E/F/G's declared effects and MDE out of that module's own globals. Importing
# them here would silently grade Book H against Book F's declared effect. The
# bodies below are the same arithmetic with the book's numbers passed IN, which
# is the difference between reuse and a shared mutable assumption.


def recompute_mde(result: dict, *, nominal: float, deflated: float) -> dict:
    """The MDE from the book's OWN realised difference series.

    Both registrations promise this in section 4 — "recomputed from this book's
    own realised difference series, its own block count and its own measured
    lag-1 rho, before the decision". A promise kept only in prose is not kept.
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
            "mde_per_block": (round(mde, 6) if mde is not None else None),
            "declared_mde_nominal": nominal,
            "declared_mde_deflated": deflated,
            "why": ("the registration's pair was computed from a MODELLED "
                    "book-minus-twin sd at k=30. This is the same arithmetic on "
                    "the sd the book actually realised, and it is the number "
                    "the verdict should be read against where the two "
                    "disagree.")}


def run_cell(panel, *, book: str, label: str, select, pool_filter,
             floor_usd, seed: int) -> dict:
    """One book at one floor, with its twin re-drawn at that floor."""
    res = run_monthly(panel, select, k=K, seed=seed, label=label,
                      twin="random_universe_turnover_matched",
                      floor_usd=floor_usd, pool_filter=pool_filter)
    nominal, deflated = DECLARED_MDE[book]
    return {"label": label, "book": book,
            "floor_usd": (float(REPLAY_FLOOR_USD) if floor_usd is None
                          else float(floor_usd)),
            "floor_is_registered_primary": floor_usd is None,
            "block_unit": DECLARED_UNIT[book],
            "result": {k: v for k, v in res.items()
                       if k not in ("blocks", "excess")},
            "by_era": by_era(res),
            "mde_recomputed": recompute_mde(res, nominal=nominal,
                                            deflated=deflated),
            "_series": res}


def decide_cell(book: str, cell: dict, falsifiers: list,
                secondary: dict | None) -> dict:
    """Each draft's section 5, applied to the PRIMARY floor's cell.

    The ladder can only be read off the primary floor: section 8 of both drafts
    says both floors are printed or neither is, and section 5 makes the second
    floor a way for a CLEARED primary to be held back — never a way for a failed
    one to be promoted.
    """
    res = cell.get("result") or {}
    mean, t = res.get("mean_excess_net_monthly"), res.get("nw_lag2_t")
    declared = DECLARED_EFFECT[book]
    unit = DECLARED_UNIT[book]
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
            f"the primary metric is on the WRONG SIDE OF ZERO: {mean:+.6f}/"
            f"{unit} at NW lag-2 t {t} (section 5 clause 1, carried in this "
            f"draft from the start rather than added by amendment afterwards)")
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
                "reading": (f"the primary metric is {mean:+.6f}/{unit} at t {t} "
                            f"and no clause fired, but {undetermined} could not "
                            f"be computed. A falsifier that could not run is "
                            f"not a falsifier that passed.")}

    clears = bool(mean >= declared and t is not None and t >= T_ALIVE)
    promising = bool(clears and eras["n_positive"] >= 3
                     and sec_mean is not None and sec_mean > 0)
    if promising:
        return {"verdict": "PRODUCT_PROMISING", "clauses_fired": [],
                "era_stability": eras,
                "reading": (f"{mean:+.6f}/{unit} at t {t} clears the declared "
                            f"{declared:.4f}/{unit}, both falsifiers passed, "
                            f"the sign is positive in {eras['n_positive']}/"
                            f"{eras['n_eras_read']} eras and the $10M cell is "
                            f"{sec_mean:+.6f}/{unit}.")}
    holds = []
    if not clears:
        holds.append(f"the block mean {mean:+.6f}/{unit} at t {t} is below the "
                     f"declared {declared:.4f}/{unit} or below the |t| >= "
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


def coverage_and_contamination(panel, covered: dict, *, book: str,
                               floor_usd: float | None) -> dict:
    """Per-year coverage inside the eligible band, and the years it excludes.

    Applied BEFORE the number is read, not after it, and the excluded years are
    reported with their coverage: "we dropped 2006" and "we dropped 2006,
    coverage 0.03" are different facts.
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

    years, excluded = {}, []
    for y, rows in sorted(per_year.items()):
        elig = [a for a, _ in rows]
        cov = [b for _, b in rows]
        share = float(np.sum(cov)) / float(np.sum(elig)) if np.sum(elig) else 0.0
        med = float(np.median(cov)) if cov else 0.0
        why = []
        if share < MIN_COVERAGE_SHARE:
            why.append(f"covered share {share:.3f} < {MIN_COVERAGE_SHARE}")
        if med < MIN_COVERED_NAMES_MEDIAN:
            why.append(f"median covered names {med:.0f} < "
                       f"{MIN_COVERED_NAMES_MEDIAN}")
        years[str(y)] = {"blocks": len(rows),
                         "median_eligible_names": float(np.median(elig)),
                         "median_covered_names": med,
                         "covered_share": round(share, 4),
                         "excluded": bool(why),
                         "why": "; ".join(why) or None}
        if why:
            excluded.append(y)
    return {"clause": (f"TRIAL-DRAFT-{book}'s contamination clause: exclude a "
                       f"year whose covered share inside the eligible band "
                       f"falls below {MIN_COVERAGE_SHARE}, or whose MEDIAN "
                       f"block carries fewer than {MIN_COVERED_NAMES_MEDIAN} "
                       f"covered names"),
            "floor_usd": (float(REPLAY_FLOOR_USD) if floor_usd is None
                          else float(floor_usd)),
            "per_year": years, "excluded_years": sorted(excluded),
            "n_excluded_years": len(excluded)}


# --------------------------------------------------------------------------
# BOOK H — the grant tape, the daily windows, the expanding history


def grant_files() -> list[Path]:
    d = insider_dir()
    return sorted(d.glob("*.parquet"))


def load_grants(start: int, end: int):
    """The DERIV `trans_code == 'A'` rows with a resolved permno, PIT-stamped.

    `filing_date` is the only date this book gates on: the transaction happens
    up to two business days before anyone outside the issuer can see it, and
    this table's whole PIT defence rests on that gap being honoured.
    `acceptance_datetime_utc` exists on the table and is 100% NULL on this
    vintage — checked on 2015q1, not assumed — so `observed_at_basis` is
    `FILING_DATE_EOD_CONSERVATIVE` for every row.
    """
    import pandas as pd

    files = grant_files()
    if not files:
        raise CharacteristicPanelUnavailable(
            f"no parsed Form-4 quarters under {insider_dir()}. Book H is "
            f"`trans_code == 'A'` on that table and this job does not build "
            f"data it was asked to replay; the distilled "
            f"`insider_events_v1.parquet` is NOT a substitute, because "
            f"`sec_insider_bulk_load.py` filters every GRANT_AWARD row out of "
            f"it.")
    cols = ["permno", "issuer_cik", "owner_cik", "table", "trans_code",
            "trans_date", "filing_date"]
    frames = []
    for f in files:
        df = pd.read_parquet(f, columns=cols)
        df = df[(df["trans_code"].astype(str) == "A")
                & (df["table"].astype(str) == "DERIV")]
        df = df.dropna(subset=["permno", "trans_date", "filing_date"])
        if df.empty:
            continue
        frames.append(df)
    if not frames:
        raise CharacteristicPanelUnavailable(
            f"the parsed Form-4 quarters under {insider_dir()} carry no "
            f"`trans_code == 'A'` DERIV row with a resolved permno")
    g = pd.concat(frames, ignore_index=True)
    g["permno"] = g["permno"].astype("int64")
    g["trans_date"] = pd.to_datetime(g["trans_date"], errors="coerce")
    g["filing_date"] = pd.to_datetime(g["filing_date"], errors="coerce")
    g = g.dropna(subset=["trans_date", "filing_date"])
    lo = pd.Timestamp(f"{int(start)}-01-01")
    hi = pd.Timestamp(f"{int(end)}-12-31")
    g = g[(g["filing_date"] >= lo) & (g["filing_date"] <= hi)]
    g["pair"] = (g["issuer_cik"].astype(str) + "|"
                 + g["owner_cik"].astype(str))
    return g.reset_index(drop=True)


def load_daily_cum(start: int, end: int):
    """`daily_from_arrays` over the CRSP daily files covering `start`..`end`.

    One year either side of the window, because a grant filed in January needs
    the twenty sessions before it and one filed in December the twenty after.

    Read year by year into COMPACT numpy arrays rather than concatenated into
    one 19-million-row DataFrame. That is not tidiness: on the machine this job
    runs on the model server holds most of the RAM, and the DataFrame route
    peaks at roughly three times what the arrays do, on a step whose output is
    six flat vectors.
    """
    import numpy as np
    import pandas as pd

    pns, dts, rets = [], [], []
    for y in range(int(start) - 1, int(end) + 2):
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if not p.is_file():
            continue
        df = pd.read_parquet(p, columns=["permno", "date", "ret"])
        df = df.dropna(subset=["ret"])
        pns.append(df["permno"].to_numpy(dtype="int32"))
        dts.append(pd.to_datetime(df["date"]).to_numpy(dtype="datetime64[ns]"))
        rets.append(df["ret"].to_numpy(dtype="float64"))
        del df
    if not pns:
        raise CharacteristicPanelUnavailable(
            f"no CRSP daily files under {wrds_dir()}; Book H's pre/post grant "
            f"windows are measured in TRADING SESSIONS and a monthly panel "
            f"cannot supply them")
    return daily_from_arrays(np.concatenate(pns), np.concatenate(dts),
                             np.concatenate(rets))


def daily_from_frame(d):
    """`daily_from_arrays` from a DataFrame of `permno, date, ret`.

    The shape the tests drive, with three names instead of nineteen million
    rows.
    """
    import pandas as pd

    return daily_from_arrays(
        d["permno"].to_numpy(dtype="int32"),
        pd.to_datetime(d["date"]).to_numpy(dtype="datetime64[ns]"),
        d["ret"].to_numpy(dtype="float64"))


def daily_from_arrays(permno, date, ret):
    """Per-name cumulative log returns on a shared session calendar.

    A sorted array of every session in the window, and for each permno a slice
    of its own session indices and cumulative log returns, plus the
    equal-weight cross-sectional cumulative log return of the market on the
    SAME calendar. The market leg is what makes the grant windows
    market-ADJUSTED rather than raw, which is what the registration froze.
    """
    import numpy as np

    sessions = np.unique(date)
    sidx_all = np.searchsorted(sessions, date).astype("int32")
    lg = np.log1p(np.clip(ret, -0.999999, None))

    # The market: the equal-weight cross-sectional mean SIMPLE return of every
    # name trading that session, then its cumulative log. Equal weight because
    # the book is equal weight; a value-weighted adjustment would grade a book
    # against a benchmark it does not hold.
    tot = np.bincount(sidx_all, weights=ret, minlength=len(sessions))
    cnt = np.bincount(sidx_all, minlength=len(sessions)).astype(float)
    mkt = np.where(cnt > 0, tot / np.maximum(cnt, 1.0), 0.0)
    mkt_cum = np.concatenate([[0.0], np.cumsum(np.log1p(mkt))])
    del tot, cnt, mkt

    order = np.lexsort((sidx_all, permno))
    perm = permno[order]
    sidx = sidx_all[order]
    cum = np.concatenate([[0.0], np.cumsum(lg[order])])
    del lg, order, sidx_all
    # ONE sorted key over (permno, session) so a grant's position inside its own
    # name's block is a single vectorised `searchsorted` and not a Python loop
    # over a million grants. `SESSION_KEY_BASE` is larger than any session index
    # this window can produce, which is what makes the composite key order the
    # same way the lexsort did.
    key = perm.astype("int64") * SESSION_KEY_BASE + sidx.astype("int64")
    starts = np.flatnonzero(np.r_[True, perm[1:] != perm[:-1]])
    return {"sessions": sessions, "perm": perm, "sidx": sidx, "cum": cum,
            "starts": starts, "name_ids": perm[starts],
            "ends": np.r_[starts[1:], len(perm)], "key": key,
            "mkt_cum": mkt_cum, "n": len(perm)}


def grant_windows(daily: dict, permnos, dates, *, window: int = GRANT_WINDOW):
    """(pre, post) market-adjusted log returns around each (permno, date).

    `pre` spans the `window` sessions strictly BEFORE the first session at or
    after the grant date; `post` the `window` sessions strictly after it, both
    minus the equal-weight market over the IDENTICAL calendar sessions. A grant
    whose name has too little tape on either side yields NaN — dropped, never
    imputed, because an imputed window would be a return nobody earned.
    """
    import numpy as np

    sessions = daily["sessions"]
    sidx, cum, key = daily["sidx"], daily["cum"], daily["key"]
    starts, name_ids, ends = daily["starts"], daily["name_ids"], daily["ends"]
    mkt_cum = daily["mkt_cum"]

    pn = np.asarray(permnos, dtype="int64")
    ts = np.asarray(dates, dtype="datetime64[ns]")
    j = np.searchsorted(name_ids, pn)
    ok = j < len(name_ids)
    j = np.clip(j, 0, max(len(name_ids) - 1, 0))
    ok &= name_ids[j] == pn

    lo, hi = starts[j], ends[j]
    g = np.searchsorted(sessions, ts)            # global session at/after grant
    k = np.searchsorted(key, pn * SESSION_KEY_BASE + g.astype("int64"),
                        side="left")
    ok &= (k - window >= lo) & (k + window < hi)

    pre = np.full(len(pn), np.nan)
    post = np.full(len(pn), np.nan)
    idx = np.flatnonzero(ok)
    if idx.size:
        k_ok = k[idx]
        pre_own = cum[k_ok] - cum[k_ok - window]
        post_own = cum[k_ok + window + 1] - cum[k_ok + 1]
        pre_mkt = mkt_cum[sidx[k_ok - 1] + 1] - mkt_cum[sidx[k_ok - window]]
        post_mkt = mkt_cum[sidx[k_ok + window] + 1] - mkt_cum[sidx[k_ok + 1]]
        pre[idx] = pre_own - pre_mkt
        post[idx] = post_own - post_mkt
    return pre, post


def pair_state_rows(grants):
    """One row per grant from the MIN_PRIOR_GRANTS-th on: the pair's state.

    The state is the EXPANDING mean of that pair's `pre` and `post` over every
    grant it has FILED so far, and the month it becomes readable is the grant's
    own filing month — a Form-4 filed in month m is public at 22:00 ET that day
    and therefore known at month m's close.
    """
    import pandas as pd

    from backend.services.book_signals import MIN_PRIOR_GRANTS

    cols = ["pair", "permno", "ym", "n_prior_grants", "mean_pre", "mean_post",
            "grant_class"]
    g = grants.dropna(subset=["pre", "post"]).copy()
    if g.empty:
        return pd.DataFrame(columns=cols)
    g = g.sort_values(["pair", "filing_date"], kind="mergesort").copy()
    grp = g.groupby("pair", sort=False)
    g["n_prior_grants"] = grp.cumcount() + 1
    g["mean_pre"] = grp["pre"].cumsum() / g["n_prior_grants"]
    g["mean_post"] = grp["post"].cumsum() / g["n_prior_grants"]
    g = g[g["n_prior_grants"] >= int(MIN_PRIOR_GRANTS)].copy()
    g["ym"] = pd.PeriodIndex(g["filing_date"], freq="M")
    # The state that matters in a month is the LAST one filed by that month.
    g = g.drop_duplicates(subset=["pair", "ym"], keep="last")
    return g[cols].reset_index(drop=True)


def expand_pair_months(states, months):
    """{ym: pair-level frame} — each pair's latest state carried forward.

    A pair's state is valid from the month it was filed until the month before
    its next state row, or to the end of the window. Expanding it here once,
    with `np.repeat`, is what lets every cell of every floor read the same
    frames without rebuilding them; the alternative is a per-month asof-join
    inside a selector that is called a couple of thousand times.
    """
    import numpy as np
    import pandas as pd

    if states.empty:
        return {}
    month_ord = {m: i for i, m in enumerate(months)}
    s = states[states["ym"].isin(set(month_ord))].copy()
    if s.empty:
        return {}
    s["start"] = s["ym"].map(month_ord).astype("int64")
    s = s.sort_values(["pair", "start"], kind="mergesort")
    nxt = s.groupby("pair", sort=False)["start"].shift(-1)
    s["stop"] = nxt.fillna(len(months)).astype("int64")
    span = (s["stop"] - s["start"]).to_numpy()
    total = int(span.sum())
    if total > MAX_PAIR_MONTHS:
        raise CharacteristicPanelUnavailable(
            f"the (pair, month) expansion is {total:,} rows, above the "
            f"{MAX_PAIR_MONTHS:,} guard. This is a REFUSAL by name rather than "
            f"an out-of-memory kill at 03:00 that writes no receipt at all")
    rep = np.repeat(np.arange(len(s)), span)
    offset = np.arange(total) - np.repeat(np.cumsum(np.r_[0, span[:-1]]), span)
    ym_ord = np.repeat(s["start"].to_numpy(), span) + offset
    # COMPACT dtypes, deliberately. This frame is the largest object the job
    # builds -- roughly fifteen million rows over the registered window, and
    # twice that with the placebo alive beside it -- and the machine it runs on
    # has the model server holding most of its RAM. `owner_cik` is carried as
    # the pair's integer CODE rather than its CIK string: the signal requires
    # the column to EXIST (it is part of the declared pair-level contract) and
    # never reads its value, and fifteen million object pointers to repeated
    # strings is a hundred megabytes spent on nothing.
    pair_codes = pd.factorize(s["pair"], sort=False)[0].astype("int32")
    long = pd.DataFrame({
        "ym_ord": ym_ord.astype("int32"),
        "permno": s["permno"].to_numpy(dtype="int32")[rep],
        "owner_cik": pair_codes[rep],
        "mean_pre": s["mean_pre"].to_numpy(dtype="float32")[rep],
        "mean_post": s["mean_post"].to_numpy(dtype="float32")[rep],
        "n_prior_grants": s["n_prior_grants"].to_numpy(dtype="int16")[rep],
        "grant_class": pd.Categorical(s["grant_class"].to_numpy()[rep]),
    })
    return {months[int(o)]: sub.drop(columns=["ym_ord"])
            for o, sub in long.groupby("ym_ord", sort=False)}


def classify_scheduled(grants):
    """A pandas Series of SCHEDULED / UNSCHEDULED / UNCLASSIFIABLE per grant.

    `sec_insider_bulk.classify_routine_opportunistic` is the rule this
    repository already pinned against `cmp_insider.classify_buy`: three
    strictly-prior years of activity with the SAME calendar month in all three
    is ROUTINE. It is CALLED here rather than re-implemented, so Book H's
    "scheduled" and the CMP trials' "routine" cannot drift apart.

    The history handed to it is built from that (issuer, insider) pair's own
    STRICTLY PRIOR grants — the row being classified is added to the history
    only after it has been classified — so no grant classifies itself. A pair
    with too little history comes back UNCLASSIFIABLE and is never defaulted to
    either side; TRIAL-DRAFT-H section 5 clause 3 reads those as untestable,
    which is why the returned value is the three-way verdict and not a bool.
    """
    import pandas as pd

    from backend.services.sec_insider_bulk import (
        classify_routine_opportunistic, normalise_cik)

    # The history is CHRONOLOGICAL per pair, so the classification must walk the
    # grants in that order and be mapped back to the caller's own row order.
    g = grants.sort_values(["pair", "trans_date"], kind="mergesort")
    out, hist = [], {}
    for pair, owner, td in zip(g["pair"], g["owner_cik"], g["trans_date"]):
        h = hist.setdefault(pair, {"years": set(), "year_months": set()})
        key = normalise_cik(owner)
        out.append(classify_routine_opportunistic(owner, td, {key: h})
                   if key else "unclassifiable")
        h["years"].add(td.year)
        h["year_months"].add(f"{td.year}-{td.month:02d}")
    return pd.Series(out, index=g.index).reindex(grants.index)


def build_book_h(grants, daily, months, *, placebo: bool = False,
                 seed: int = 0):
    """The pair-month frames Book H (or its registered placebo) is scored on.

    `grants` and `daily` are passed IN rather than loaded here, because the
    placebo is the same tape read around a different date and re-reading
    nineteen years of CRSP daily to shift a column would double the slowest
    step in the job for nothing.
    """
    import numpy as np
    import pandas as pd

    dates = grants["trans_date"]
    if placebo:
        # THE REGISTERED PLACEBO (TRIAL-DRAFT-H section 5 clause 2): the same
        # insider, the same firm, the same FILING-date gate, and a grant date
        # relabelled 90-180 days away from the true one in a random direction.
        # If ranking issuers on pre/post windows around a date where NOTHING
        # happened pays as well, what was measured is name-level return
        # persistence in the insider's firms and not grant timing.
        rng = np.random.default_rng(int(seed))
        off = rng.integers(PLACEBO_OFFSET_DAYS[0], PLACEBO_OFFSET_DAYS[1] + 1,
                           size=len(grants))
        sign = rng.choice(np.array([-1, 1]), size=len(grants))
        dates = dates + pd.to_timedelta(off * sign, unit="D")

    pre, post = grant_windows(daily, grants["permno"].to_numpy(),
                              dates.to_numpy())
    grants = grants.assign(pre=pre, post=post)
    verdicts = classify_scheduled(grants)
    grants = grants.assign(grant_class=verdicts)
    states = pair_state_rows(grants)
    frames = expand_pair_months(states, months)
    # The pool filter's OWN requirement: the issuer must carry a resolved-permno
    # DERIV grant filed in the trailing 36 months. A grant history from 2008 is
    # not a governance characteristic of a 2024 issuer.
    recent: dict = {}
    fym = pd.PeriodIndex(grants["filing_date"], freq="M")
    by_fym: dict = {}
    for ym, pn in zip(fym, grants["permno"]):
        by_fym.setdefault(ym, set()).add(int(pn))
    for m in months:
        acc: set = set()
        for back in range(GRANT_RECENCY_MONTHS):
            acc |= by_fym.get(m - back, set())
        recent[m] = acc
    covered = {m: ({int(p) for p in frames[m]["permno"]} & recent.get(m, set()))
               for m in frames}
    cls = verdicts.value_counts(dropna=False).to_dict()
    stats = {
        "grant_rows_read": int(len(grants)),
        "grant_rows_with_a_computable_window": int(np.isfinite(pre).sum()),
        "pairs": int(grants["pair"].nunique()),
        "pair_state_rows": int(len(states)),
        "pair_months_expanded": int(sum(len(f) for f in frames.values())),
        "months_with_a_frame": len(frames),
        "grant_class_counts": {str(k): int(v) for k, v in cls.items()},
        "grant_class_note": ("UNCLASSIFIABLE grants belong to NEITHER leg of "
                             "section 5 clause 3. A pair with too little "
                             "history is not evidence that its grants were "
                             "unscheduled, and folding it into the unscheduled "
                             "leg would be exactly the default the CMP rule "
                             "refuses to make."),
        "is_placebo": bool(placebo),
    }
    return frames, covered, stats


def book_h_selector(frames: dict, *, side: str = "top",
                    subset: str | None = None):
    """Book H's selector. `subset` splits the registered falsifier's two legs.

    `subset='unscheduled'` / `'scheduled'` filters the PAIR rows before the
    issuer median is taken, which is the only place the split can honestly
    happen: an issuer whose scheduled and unscheduled insiders disagree belongs
    to both legs with different statistics, not to whichever leg it was first
    assigned to.

    An UNCLASSIFIABLE pair — one without the three strictly-prior years the CMP
    rule needs — is in NEITHER subset. Folding it into `unscheduled` would make
    "we could not tell" into evidence, which is the default that rule exists to
    refuse.
    """
    from backend.services import book_signals as BS

    def select(pool, ym):
        g = frames.get(ym)
        if g is None or g.empty:
            return []
        sub = g[g["permno"].isin(set(pool["permno"].astype("int64")))]
        if subset == "unscheduled":
            sub = sub[sub["grant_class"].astype(str) == "opportunistic"]
        elif subset == "scheduled":
            sub = sub[sub["grant_class"].astype(str) == "routine"]
        if sub.empty:
            return []
        try:
            scores = BS.option_grant_timing_score(sub, side=side,
                                                  tercile=TERCILE)
        except BS.SignalUnavailable:
            return []
        rev = (side == "top")
        return [p for p, _ in sorted(scores.items(),
                                     key=lambda kv: ((-kv[1], kv[0]) if rev
                                                     else (kv[1], kv[0])))]
    return select


# --------------------------------------------------------------------------
# BOOK I — the quarterly panel, the buyback leg, the sale leg


def to_quarterly(panel):
    """The monthly CRSP panel, pre-aggregated into quarterly `ym` buckets.

    Returns compound, price is the quarter's last month's close, dollar volume
    is the MEDIAN of its months (so the floor means the same thing it means
    monthly) and turnover sums. `run_monthly` is then run over these buckets
    unmodified — `Period[Q]` carries `.year` and `.month`, which is everything
    the engine reads off a period.
    """
    import numpy as np
    import pandas as pd

    p = panel.copy()
    p["q"] = pd.PeriodIndex(p["ym"], freq="M").asfreq("Q")
    p["lg"] = np.log1p(np.clip(p["ret_m"].astype(float), -0.999999, None))
    g = p.groupby(["permno", "q"], sort=False).agg(
        lg=("lg", "sum"), n=("lg", "size"), dv=("dv", "median"),
        price=("price", "last"), turnover_m=("turnover_m", "sum")).reset_index()
    g = g[g["n"] >= 2]
    g["ret_m"] = np.expm1(g["lg"])
    g = g.rename(columns={"q": "ym"})
    return (g[["permno", "ym", "ret_m", "price", "dv", "turnover_m"]]
            .sort_values(["ym", "permno"], kind="mergesort")
            .reset_index(drop=True))


def load_buyback_rows(start: int, end: int):
    """The linked, PIT-stamped `prstkc` rows, with the basis counted per row.

    `funda` has NO `rdq` column — that is a `fundq` field, verified on disk on
    2026-09-14. The availability stamp is `max(pdate, fdate)` where either is
    present and `datadate + 180 days` otherwise; 180 rather than 90 because the
    measured `pdate` lag is already 125 days at the ninetieth percentile, so a
    90-day fallback would make a fifth of the fallback rows readable before
    Compustat itself had them. `apdedate` is NOT used: its measured lag behind
    `datadate` is zero days at the median AND at q90 — it is the period end, not
    a publication date, and reading it as one is look-ahead in a column that
    looks like a PIT stamp.
    """
    import numpy as np
    import pandas as pd

    f = wrds_dir() / "bulk" / "comp__funda.parquet"
    lk = wrds_dir() / "link_ccm.parquet"
    if not f.is_file() or not lk.is_file():
        raise CharacteristicPanelUnavailable(
            f"Book I needs both {f} and {lk}; `prstkc` is a Compustat annual "
            f"field and `link_ccm` is the only gvkey->permno map on disk, and "
            f"this job does not guess a join")
    d = pd.read_parquet(f, columns=list(FUNDA_COLUMNS))
    for col, want in FUNDA_FILTER.items():
        d = d[d[col].astype(str) == want]
    d["datadate"] = pd.to_datetime(d["datadate"])
    have = d[["pdate", "fdate"]].max(axis=1)
    d["available_date"] = have.fillna(d["datadate"]
                                      + pd.Timedelta(days=BUYBACK_FALLBACK_DAYS))
    d["available_basis"] = np.where(have.notna(), "COMPUSTAT_PDATE_OR_FDATE",
                                    "DATADATE_PLUS_180D_CONSERVATIVE")
    lo = pd.Timestamp(f"{int(start) - 2}-01-01")
    hi = pd.Timestamp(f"{int(end)}-12-31")
    d = d[(d["available_date"] >= lo) & (d["available_date"] <= hi)]
    d = d.dropna(subset=["prstkc"])

    link = pd.read_parquet(lk, columns=list(LINK_COLUMNS))
    link = link[link["linktype"].astype(str).isin(LINK_TYPES)
                & link["linkprim"].astype(str).isin(LINK_PRIMS)]
    link["linkdt"] = pd.to_datetime(link["linkdt"])
    link["linkenddt"] = pd.to_datetime(link["linkenddt"]).fillna(
        pd.Timestamp("2100-01-01"))
    m = d.merge(link[["gvkey", "permno", "linkdt", "linkenddt"]], on="gvkey",
                how="inner")
    # The link must bracket the AVAILABILITY date, not the `datadate`: the row
    # is read when it becomes public, and that is when the identifier has to be
    # the right one.
    m = m[(m["available_date"] >= m["linkdt"])
          & (m["available_date"] <= m["linkenddt"])]
    m = m.dropna(subset=["permno"])
    m["permno"] = m["permno"].astype("int64")
    mcap = m["csho"].astype(float) * m["prcc_f"].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        m["buyback_intensity"] = np.where(mcap > 0,
                                          m["prstkc"].astype(float) / mcap, 0.0)
    m["buyback_intensity"] = m["buyback_intensity"].replace(
        [np.inf, -np.inf], 0.0).fillna(0.0).clip(lower=0.0)
    m["buyback_flag"] = m["prstkc"].astype(float) > 0.0
    return m[["permno", "available_date", "available_basis", "prstkc",
              "buyback_flag", "buyback_intensity"]].sort_values(
                  "available_date", kind="mergesort").reset_index(drop=True)


def load_sale_rows(start: int, end: int):
    """The `trans_code == 'S'` NONDERIV disposals, and every Form-4 filing date.

    Two products from one pass over the 82 quarters: the sale rows the intensity
    is computed from, and the (permno, filing_date) pairs the pool filter's
    Form-4 coverage requirement needs. Reading the tape twice for those would
    double the slowest IO in the job.
    """
    import pandas as pd

    files = grant_files()
    if not files:
        raise CharacteristicPanelUnavailable(
            f"no parsed Form-4 quarters under {insider_dir()}; Book I's sale "
            f"leg has no substitute on disk")
    sales, cover = [], []
    lo = pd.Timestamp(f"{int(start) - 2}-01-01")
    hi = pd.Timestamp(f"{int(end)}-12-31")
    for f in files:
        df = pd.read_parquet(f, columns=list(INSIDER_COLUMNS))
        df = df.dropna(subset=["permno", "filing_date"])
        if df.empty:
            continue
        df["permno"] = df["permno"].astype("int64")
        df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
        df = df.dropna(subset=["filing_date"])
        df = df[(df["filing_date"] >= lo) & (df["filing_date"] <= hi)]
        if df.empty:
            continue
        cover.append(df[["permno", "filing_date"]])
        s = df[(df["trans_code"].astype(str) == "S")
               & (df["table"].astype(str) == "NONDERIV")
               & (df["acquired_disposed"].astype(str) == "D")]
        if not s.empty:
            sales.append(s[["permno", "owner_cik", "shares",
                            "shares_owned_following", "filing_date",
                            "plan_10b5_1"]])
    if not cover:
        raise CharacteristicPanelUnavailable(
            "the parsed Form-4 quarters carry no row with a resolved permno in "
            "the read window")
    cov = pd.concat(cover, ignore_index=True).sort_values(
        "filing_date", kind="mergesort").reset_index(drop=True)
    if sales:
        sl = pd.concat(sales, ignore_index=True)
        sl["shares"] = sl["shares"].astype(float)
        sl["shares_owned_following"] = sl["shares_owned_following"].astype(float)
        sl = sl.dropna(subset=["shares"])
        sl = sl.sort_values("filing_date", kind="mergesort").reset_index(drop=True)
    else:
        sl = pd.DataFrame(columns=["permno", "owner_cik", "shares",
                                   "shares_owned_following", "filing_date",
                                   "plan_10b5_1"])
    return sl, cov


def sell_intensity(sales, qend, *, exclude_10b5_1: bool = False,
                   large_only: bool = False, small_only: bool = False):
    """{permno: share of holdings disposed} over the trailing 90 days.

    `sold / (sold + still held)` at the ISSUER level, where "still held" is each
    insider's `shares_owned_following` at their LAST filing inside the window.
    Bounded in [0, 1] by construction, which is what makes it comparable across
    firms of very different share counts — a dollar total is not.

    A name with no sale in the window scores ZERO, and the caller must supply
    that zero rather than a NaN: `buyback_insider_divergence` drops a NaN and
    keeps a zero, and the difference is the whole low-selling leg.
    """
    import numpy as np
    import pandas as pd

    if sales.empty:
        return {}
    end = pd.Timestamp(qend)
    begin = end - pd.Timedelta(days=SALE_WINDOW_DAYS)
    fd = sales["filing_date"].to_numpy()
    a = int(np.searchsorted(fd, np.datetime64(begin), side="right"))
    b = int(np.searchsorted(fd, np.datetime64(end), side="right"))
    w = sales.iloc[a:b]
    if w.empty:
        return {}
    if exclude_10b5_1:
        w = w[w["plan_10b5_1"].astype(str) != "YES"]
    if large_only or small_only:
        held = w["shares_owned_following"].astype(float)
        share = w["shares"].astype(float) / (w["shares"].astype(float)
                                             + held.fillna(0.0)).replace(0.0, np.nan)
        keep = (share >= LARGE_SALE_SHARE) if large_only else (share < LARGE_SALE_SHARE)
        w = w[keep.fillna(False)]
    if w.empty:
        return {}
    sold = w.groupby(["permno", "owner_cik"], sort=False)["shares"].sum()
    last = (w.sort_values("filing_date", kind="mergesort")
            .drop_duplicates(subset=["permno", "owner_cik"], keep="last")
            .set_index(["permno", "owner_cik"])["shares_owned_following"])
    held = last.reindex(sold.index).fillna(0.0).astype(float)
    per_issuer = pd.DataFrame({"sold": sold, "held": held}).groupby(
        level=0).sum()
    denom = (per_issuer["sold"] + per_issuer["held"]).replace(0.0, np.nan)
    out = (per_issuer["sold"] / denom).fillna(0.0).clip(0.0, 1.0)
    return {int(k): float(v) for k, v in out.items()}


def build_book_i(start: int, end: int, quarters):
    """{ym: per-name frame} for the divergence, plus the reported variants."""
    import numpy as np
    import pandas as pd

    bb = load_buyback_rows(start, end)
    sales, cover = load_sale_rows(start, end)

    bb_dates = bb["available_date"].to_numpy()
    cov_dates = cover["filing_date"].to_numpy()
    frames, covered = {}, {}
    variants = {"excl_10b5_1": {}, "large_sales_only": {}, "small_sales_only": {}}
    basis_counts = {"COMPUSTAT_PDATE_OR_FDATE": 0,
                    "DATADATE_PLUS_180D_CONSERVATIVE": 0}
    for q in quarters:
        qend = q.to_timestamp(how="end").normalize()
        recent = qend - pd.DateOffset(months=BUYBACK_RECENCY_MONTHS)
        a = int(np.searchsorted(bb_dates, np.datetime64(recent), side="right"))
        b = int(np.searchsorted(bb_dates, np.datetime64(qend), side="right"))
        win = bb.iloc[a:b]
        if win.empty:
            continue
        cur = win.drop_duplicates(subset=["permno"], keep="last")
        for k, v in cur["available_basis"].value_counts().items():
            basis_counts[str(k)] = basis_counts.get(str(k), 0) + int(v)

        c0 = int(np.searchsorted(cov_dates,
                                 np.datetime64(qend - pd.Timedelta(
                                     days=FORM4_COVERAGE_DAYS)), side="right"))
        c1 = int(np.searchsorted(cov_dates, np.datetime64(qend), side="right"))
        form4 = set(int(p) for p in cover["permno"].to_numpy()[c0:c1])
        band = [int(p) for p in cur["permno"] if int(p) in form4]
        if not band:
            continue
        sub = cur[cur["permno"].isin(set(band))]
        base = sell_intensity(sales, qend)
        frames[q] = pd.DataFrame({
            "permno": sub["permno"].to_numpy(),
            "buyback_flag": sub["buyback_flag"].to_numpy(),
            "buyback_intensity": sub["buyback_intensity"].to_numpy(),
            "sell_intensity": [base.get(int(p), 0.0) for p in sub["permno"]],
        })
        for name, kw in (("excl_10b5_1", {"exclude_10b5_1": True}),
                         ("large_sales_only", {"large_only": True}),
                         ("small_sales_only", {"small_only": True})):
            alt = sell_intensity(sales, qend, **kw)
            variants[name][q] = frames[q].assign(
                sell_intensity=[alt.get(int(p), 0.0) for p in sub["permno"]])
        covered[q] = set(band)
    stats = {
        "buyback_rows_linked": int(len(bb)),
        "sale_rows": int(len(sales)),
        "form4_filing_rows": int(len(cover)),
        "quarters_with_a_frame": len(frames),
        "availability_basis_counts": basis_counts,
        "availability_basis_note": (
            "counted per (permno, quarter) SELECTION, not per funda row: the "
            "same annual row is the current one for several quarters and each "
            "of those readings is what a PIT claim is actually about"),
    }
    return frames, variants, covered, stats


def book_i_selector(frames: dict, *, leg: str = "divergence", seed: int = 0):
    from backend.services import book_signals as BS

    def select(pool, ym):
        g = frames.get(ym)
        if g is None or g.empty:
            return []
        sub = g[g["permno"].isin(set(pool["permno"].astype("int64")))]
        if sub.empty:
            return []
        try:
            scores = BS.buyback_insider_divergence(sub, leg=leg,
                                                   tercile=TERCILE, seed=seed)
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(scores.items(),
                                     key=lambda kv: (-kv[1], kv[0]))]
    return select


# --------------------------------------------------------------------------
# the per-book payload


def _strip(cell: dict) -> dict:
    return {k: v for k, v in cell.items() if k != "_series"}


def _p(cell: dict):
    return ((cell or {}).get("result") or {}).get("p_two_sided")


def _book_payload(key: str, label: str, prereg: str, cells: dict,
                  falsifiers: list, falsifier_blocks: dict, contamination: dict,
                  verdict: dict, *, smoke: bool, construction: dict,
                  panel_stats: dict) -> dict:
    p = cells["primary_floor"]["result"]
    s = cells["secondary_floor"]["result"]
    unit = DECLARED_UNIT[key]
    return {
        "book": label, "book_key": key, "prereg": prereg,
        "family": FAMILY, "licence": "PRODUCT_EXPERIMENT", "signed": False,
        "ran": bool(p.get("mean_excess_net_monthly") is not None),
        "primary_metric": f"net_{unit}ly_excess_vs_random_twin",
        "block_unit": unit,
        "panel_stats": panel_stats,
        "registered_construction": {
            **construction,
            "block_unit": unit,
            "k": K, "tercile": TERCILE,
            "floors_usd": {"primary": float(REPLAY_FLOOR_USD),
                           "secondary": float(SECONDARY_FLOOR_USD)},
            "min_price_usd": 5.0,
            "cost_curve": COST_CURVE,
            "cost_bps_per_side": COST_BPS_PER_SIDE,
            "declared_effect_size": DECLARED_EFFECT[key],
            "declared_mde_nominal": DECLARED_MDE[key][0],
            "declared_mde_deflated": DECLARED_MDE[key][1],
            "honours_the_registration": bool(not smoke),
            "why": ("printed in full because Book C's run 1 said "
                    "`confirm_slice 1995-2024` while warming a 60-month "
                    "overhang at 24 months. A receipt that does not print its "
                    "own construction cannot be checked against the "
                    "registration that licensed it. A SMOKE run cannot honour "
                    "the registered window and says so here rather than being "
                    "mistaken for it."),
        },
        "cells": {"primary_floor": _strip(cells["primary_floor"]),
                  "secondary_floor": _strip(cells["secondary_floor"])},
        "falsifiers": falsifiers,
        "falsifier_cells": {k: {n: _strip(c) for n, c in v.items()}
                            for k, v in falsifier_blocks.items()},
        "contamination": contamination,
        "era_stability": {"primary_floor": era_stability(cells["primary_floor"]),
                          "secondary_floor": era_stability(cells["secondary_floor"])},
        "verdict_block": verdict,
        "verdict": verdict["verdict"] + " — " + verdict["reading"],
        "both_floors_or_neither": (
            "TRIAL-DRAFT-A section 8's rule, applied here for the same reason: "
            "a book quoted at the floor that flatters it is a book quoted at a "
            "chosen corner. Both cells are above; neither may travel alone."),
        "headline": (
            f"{label}: $3M {p.get('mean_excess_net_monthly')}/{unit} t "
            f"{p.get('nw_lag2_t')} over {p.get('n_blocks')} blocks (median "
            f"{p.get('median_names_selected')} names) | $10M "
            f"{s.get('mean_excess_net_monthly')}/{unit} t "
            f"{s.get('nw_lag2_t')} over {s.get('n_blocks')} blocks -> "
            f"{verdict['verdict']}"),
        "smoke": bool(smoke),
    }


# --------------------------------------------------------------------------
# BOOK H's replay


def replay_book_h(panel, frames: dict, covered: dict, placebo_frames: dict,
                  placebo_covered: dict, *, smoke: bool,
                  panel_stats: dict) -> dict:
    cells, falsifier_blocks, contamination = {}, {}, {}
    for name, floor in (("primary_floor", PRIMARY_FLOOR_USD),
                        ("secondary_floor", SECONDARY_FLOOR_USD)):
        cont = coverage_and_contamination(panel, covered, book="H",
                                          floor_usd=floor)
        contamination[name] = cont
        skip = set(cont["excluded_years"])
        pf = _pool_filter(covered, skip)
        cells[name] = run_cell(panel, book="H", label="option_grant_timing_v0",
                               select=book_h_selector(frames),
                               pool_filter=pf, floor_usd=floor,
                               seed=SEEDS["H"])
        legs = {
            "random_date_placebo": run_cell(
                panel, book="H", label="option_grant_timing_random_date_placebo",
                select=book_h_selector(placebo_frames),
                pool_filter=_pool_filter(placebo_covered, skip),
                floor_usd=floor, seed=SEEDS["H"]),
            "unscheduled_only": run_cell(
                panel, book="H", label="option_grant_timing_unscheduled_only",
                select=book_h_selector(frames, subset="unscheduled"),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["H"]),
            "scheduled_only": run_cell(
                panel, book="H", label="option_grant_timing_scheduled_only",
                select=book_h_selector(frames, subset="scheduled"),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["H"]),
        }
        if floor is PRIMARY_FLOOR_USD:
            legs["bottom_tercile_reported_only"] = run_cell(
                panel, book="H", label="option_grant_timing_bottom_reported_only",
                select=book_h_selector(frames, side="bottom"),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["H"])
        falsifier_blocks[name] = legs

    pl = falsifier_blocks["primary_floor"]["random_date_placebo"]
    pl_mean = (pl.get("result") or {}).get("mean_excess_net_monthly")
    pl_t = (pl.get("result") or {}).get("nw_lag2_t")
    un = falsifier_blocks["primary_floor"]["unscheduled_only"]
    sc = falsifier_blocks["primary_floor"]["scheduled_only"]
    un_mean = (un.get("result") or {}).get("mean_excess_net_monthly")
    sc_mean = (sc.get("result") or {}).get("mean_excess_net_monthly")
    sc_t = (sc.get("result") or {}).get("nw_lag2_t")
    un_n = (un.get("result") or {}).get("n_blocks") or 0
    sc_n = (sc.get("result") or {}).get("n_blocks") or 0
    testable = bool(un_n >= 24 and sc_n >= 24 and un_mean is not None
                    and sc_mean is not None and sc_t is not None)

    falsifiers = [
        {"falsifier": "random_date_placebo",
         "registered_as": ("TRIAL-DRAFT-H section 5 clause 2: the same score "
                           "recomputed with each grant's `trans_date` "
                           "relabelled to a pseudo-date drawn 90-180 days away "
                           "from the true one, same insider, same issuer, same "
                           "filing-date gate. It must be indistinguishable "
                           "from zero at the |t| >= 2.0 line."),
         "placebo_mean_excess_net_monthly": pl_mean, "placebo_nw_lag2_t": pl_t,
         "fires": (None if pl_mean is None or pl_t is None
                   else bool(pl_mean > 0 and abs(pl_t) >= T_ALIVE)),
         "undetermined_because": (None if (pl_mean is not None
                                           and pl_t is not None)
                                  else "the placebo cell produced no block "
                                       "mean, so the clause could not run"),
         "clause": (f"the random-date placebo ALSO pays ({pl_mean}/month, t "
                    f"{pl_t}), so what was measured is name-level return "
                    f"persistence in the insider's firms and not grant-timing "
                    f"skill (section 5 clause 2)")},
        {"falsifier": "the_effect_must_live_in_the_UNSCHEDULED_grants",
         "registered_as": ("TRIAL-DRAFT-H section 5 clause 3: grants split by "
                           "`sec_insider_bulk.classify_routine_opportunistic` "
                           "— the same calendar month in each of three "
                           "strictly-prior years is SCHEDULED. If the SCHEDULED "
                           "subset pays at |t| >= 2.0 and at least as much as "
                           "the unscheduled subset, the effect is "
                           "scheduled-grant calendar mechanics and the "
                           "'opportunistic' framing is falsified."),
         "unscheduled_mean_excess_net_monthly": un_mean,
         "unscheduled_nw_lag2_t": (un.get("result") or {}).get("nw_lag2_t"),
         "unscheduled_n_blocks": un_n,
         "scheduled_mean_excess_net_monthly": sc_mean,
         "scheduled_nw_lag2_t": sc_t, "scheduled_n_blocks": sc_n,
         "fires": (None if not testable
                   else bool(sc_t >= T_ALIVE and sc_mean > 0
                             and sc_mean >= un_mean)),
         "undetermined_because": (None if testable else
                                  f"{un_n} unscheduled and {sc_n} scheduled "
                                  f"block(s); section 5 makes fewer than 24 on "
                                  f"either side UNTESTABLE, and a falsifier "
                                  f"that could not be computed is not a "
                                  f"falsifier that passed"),
         "clause": (f"the SCHEDULED subset pays as well as the unscheduled one "
                    f"({sc_mean}/month at t {sc_t} against {un_mean}), so the "
                    f"effect is scheduled-grant calendar mechanics and not a "
                    f"governance signal (section 5 clause 3)")},
    ]
    verdict = decide_cell("H", cells["primary_floor"], falsifiers,
                          cells["secondary_floor"])
    return _book_payload(
        "H", "option_grant_timing_v0",
        "TRIAL-DRAFT-H-option-grant-timing-v0 (UNSIGNED)",
        cells, falsifiers, falsifier_blocks, contamination, verdict,
        smoke=smoke, panel_stats=panel_stats,
        construction={
            "rows": "trans_code == 'A' AND table == 'DERIV', resolved permno",
            "pit_stamp": ("filing_date at 22:00 America/New_York "
                          "(observed_at_basis FILING_DATE_EOD_CONSERVATIVE); "
                          "acceptance_datetime_utc is 100% NULL on this "
                          "vintage, checked and not assumed"),
            "window_sessions": GRANT_WINDOW,
            "window_spans": "[-20,-1] and [+1,+20] around the grant trans_date",
            "market_adjustment": ("the equal-weight cross-sectional mean simple "
                                  "return of every CRSP name trading those same "
                                  "sessions"),
            "min_prior_grants": 3,
            "qualifying_condition": "mean_pre < 0 AND mean_post > 0",
            "statistic": "mean(post) - mean(pre)",
            "issuer_aggregation": "MEDIAN over the issuer's qualifying insiders",
            "grant_recency_months": GRANT_RECENCY_MONTHS,
            "cut": "top tercile",
            "hold": "one month, monthly rebalance",
            "twin": ("turnover-matched random draw from the SAME band of "
                     "issuers carrying a scoreable grant history"),
            "placebo_offset_days": list(PLACEBO_OFFSET_DAYS),
            "placebo_seed": PLACEBO_SEED,
        })


# --------------------------------------------------------------------------
# BOOK I's replay


def replay_book_i(qpanel, frames: dict, variants: dict, covered: dict, *,
                  smoke: bool, panel_stats: dict) -> dict:
    cells, falsifier_blocks, contamination = {}, {}, {}
    for name, floor in (("primary_floor", PRIMARY_FLOOR_USD),
                        ("secondary_floor", SECONDARY_FLOOR_USD)):
        cont = coverage_and_contamination(qpanel, covered, book="I",
                                          floor_usd=floor)
        contamination[name] = cont
        skip = set(cont["excluded_years"])
        pf = _pool_filter(covered, skip)
        cells[name] = run_cell(
            qpanel, book="I", label="buyback_insider_divergence_v0",
            select=book_i_selector(frames, leg="divergence", seed=SEEDS["I"]),
            pool_filter=pf, floor_usd=floor, seed=SEEDS["I"])
        legs = {
            "buyback_only": run_cell(
                qpanel, book="I", label="buyback_only_control",
                select=book_i_selector(frames, leg="buyback_only",
                                       seed=SEEDS["I"]),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["I"]),
            "low_selling_only": run_cell(
                qpanel, book="I", label="low_selling_only_control",
                select=book_i_selector(frames, leg="low_selling_only",
                                       seed=SEEDS["I"]),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["I"]),
            "big_half_only": run_cell(
                qpanel, book="I", label="buyback_divergence_big_half_only",
                select=book_i_selector(frames, leg="divergence",
                                       seed=SEEDS["I"]),
                pool_filter=_big_half_filter(covered, skip), floor_usd=floor,
                seed=SEEDS["I"]),
        }
        if floor is PRIMARY_FLOOR_USD:
            legs["bearish_divergence_reported_only"] = run_cell(
                qpanel, book="I", label="bearish_divergence_reported_only",
                select=book_i_selector(frames, leg="bearish_divergence",
                                       seed=SEEDS["I"]),
                pool_filter=pf, floor_usd=floor, seed=SEEDS["I"])
            for vname in ("excl_10b5_1", "large_sales_only", "small_sales_only"):
                legs[f"{vname}_reported_only"] = run_cell(
                    qpanel, book="I", label=f"divergence_{vname}_reported_only",
                    select=book_i_selector(variants[vname], leg="divergence",
                                           seed=SEEDS["I"]),
                    pool_filter=pf, floor_usd=floor, seed=SEEDS["I"])
        falsifier_blocks[name] = legs

    prim = (cells["primary_floor"].get("result") or {}).get(
        "mean_excess_net_monthly")
    bb = (falsifier_blocks["primary_floor"]["buyback_only"].get("result")
          or {}).get("mean_excess_net_monthly")
    ls = (falsifier_blocks["primary_floor"]["low_selling_only"].get("result")
          or {}).get("mean_excess_net_monthly")
    bb_n = (falsifier_blocks["primary_floor"]["buyback_only"].get("result")
            or {}).get("n_blocks") or 0
    ls_n = (falsifier_blocks["primary_floor"]["low_selling_only"].get("result")
            or {}).get("n_blocks") or 0
    big = falsifier_blocks["primary_floor"]["big_half_only"]
    big_mean = (big.get("result") or {}).get("mean_excess_net_monthly")
    big_t = (big.get("result") or {}).get("nw_lag2_t")
    legs_testable = bool(prim is not None and bb is not None and ls is not None
                         and bb_n >= 12 and ls_n >= 12)

    falsifiers = [
        {"falsifier": "the_divergence_must_beat_either_leg_alone",
         "registered_as": ("TRIAL-DRAFT-I section 5 clause 2: `buyback_only` "
                           "and `low_selling_only` on the identical pool, "
                           "floor, k, cost ruler and twin construction. If "
                           "EITHER single leg's block mean is >= the "
                           "divergence's, the conjunction adds nothing and the "
                           "book's own claim is falsified."),
         "divergence_mean": prim, "buyback_only_mean": bb,
         "low_selling_only_mean": ls,
         "buyback_only_n_blocks": bb_n, "low_selling_only_n_blocks": ls_n,
         "fires": (None if not legs_testable
                   else bool(bb >= prim or ls >= prim)),
         "undetermined_because": (None if legs_testable else
                                  f"{bb_n} buyback-only and {ls_n} "
                                  f"low-selling-only block(s); section 5 makes "
                                  f"fewer than 12 on either control UNTESTABLE"),
         "clause": (f"a single leg pays at least as well as the conjunction "
                    f"(divergence {prim}, buyback-only {bb}, low-selling-only "
                    f"{ls}), so the DIVERGENCE is not the signal "
                    f"(section 5 clause 2)")},
        {"falsifier": "survives_outside_the_smallest_names",
         "registered_as": ("TRIAL-DRAFT-I section 5 clause 3: re-run inside the "
                           "TOP HALF of the covered eligible band by dollar "
                           "volume, twin RE-DRAWN there, and require the net "
                           "excess to stay positive. The cited composite is "
                           "equal-weighted, which is the weighting that hides "
                           "a small-cap payoff."),
         "big_half_mean_excess_net_monthly": big_mean,
         "big_half_nw_lag2_t": big_t,
         "big_half_n_blocks": (big.get("result") or {}).get("n_blocks"),
         "fires": (None if big_mean is None else bool(big_mean <= 0)),
         "undetermined_because": (None if big_mean is not None else
                                  "the big-half cell produced no block mean"),
         "clause": (f"the effect does not survive outside the smallest names "
                    f"({big_mean}/quarter, t {big_t} in the top half of the "
                    f"band), so it is small-cap beta with a corporate action "
                    f"attached (section 5 clause 3)")},
    ]
    verdict = decide_cell("I", cells["primary_floor"], falsifiers,
                          cells["secondary_floor"])
    return _book_payload(
        "I", "buyback_insider_divergence_v0",
        "TRIAL-DRAFT-I-buyback-vs-insider-selling-v0 (UNSIGNED)",
        cells, falsifiers, falsifier_blocks, contamination, verdict,
        smoke=smoke, panel_stats=panel_stats,
        construction={
            "buyback_field": "prstkc (Compustat ANNUAL; fundq carries none)",
            "compustat_filter": dict(FUNDA_FILTER),
            "availability_stamp": ("max(pdate, fdate) where present, else "
                                   "datadate + 180 calendar days. `funda` has "
                                   "NO `rdq` column and `apdedate` is a period "
                                   "end, not a publication date (measured lag "
                                   "0 days at q50 AND q90)"),
            "buyback_recency_months": BUYBACK_RECENCY_MONTHS,
            "buyback_intensity": "prstkc / (csho * prcc_f) from the SAME row",
            "sale_rows": ("trans_code == 'S' AND table == 'NONDERIV' AND "
                          "acquired_disposed == 'D', stamped on filing_date"),
            "sale_window_days": SALE_WINDOW_DAYS,
            "sell_intensity": ("sum(shares sold) / (sum(shares sold) + sum("
                               "shares_owned_following at each insider's last "
                               "filing in the window)); a name with no sale "
                               "scores ZERO and that is the signal"),
            "link": (f"link_ccm, linktype in {LINK_TYPES}, linkprim in "
                     f"{LINK_PRIMS}, bracketing the AVAILABILITY date"),
            "form4_coverage_days": FORM4_COVERAGE_DAYS,
            "cut": ("BOTTOM tercile of sell_intensity among buyback names is "
                    "HELD; the TOP tercile is the reported agency-conflict cell "
                    "and is never shorted"),
            "tie_break": "sell_intensity ascending, then buyback_intensity desc",
            "cadence": ("QUARTERLY. The monthly CRSP panel is pre-aggregated "
                        "into quarterly `ym` buckets and `run_monthly` is run "
                        "over those UNMODIFIED — the spec's own preferred "
                        "option, chosen over a `rebalance_months` gate that "
                        "would change the engine five other books were read "
                        "under"),
            "hold": "one quarter, quarterly rebalance",
            "twin": ("turnover-matched random draw from the SAME band of names "
                     "with a linked available prstkc row AND Form-4 coverage"),
        })


# --------------------------------------------------------------------------
# the job


def B_books_hi_replay(*, smoke: bool = False) -> dict:            # noqa: N802
    """The night-factory entry point. One receipt, two books, two floors each."""
    t0 = datetime.now(timezone.utc)
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    panel = load_monthly_panel(start, end,
                               max_names=SMOKE_NAMES if smoke else None)
    qpanel = to_quarterly(panel)

    base = {
        "job": JOB, "family": FAMILY, "family_size_declared": 2,
        "declared_family": list(DECLARED_FAMILY),
        "licence": "PRODUCT_EXPERIMENT", "signed": False,
        "window": [start, end], "smoke": bool(smoke),
        "max_names": SMOKE_NAMES if smoke else None,
        "months_in_panel": int(panel["ym"].nunique()),
        "quarters_in_panel": int(qpanel["ym"].nunique()),
        "permnos_in_panel": int(panel["permno"].nunique()),
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "cost_caveat": ("the interim flat ruler, pending chunk 5c's TAQ curve. "
                        "Every leg of every comparison pays it, so DIFFERENCES "
                        "may be read and no LEVEL may -- and the two floors do "
                        "NOT pay the same real spread, which is exactly what a "
                        "flat ruler cannot see."),
        "question": ("Does a filer's OWN history of opportunistic option-grant "
                     "timing, and a repurchase made while its insiders are not "
                     "selling, each beat a twin drawn from their own covered "
                     "band, at both floors, 2006-2024?"),
        "eras_reported": [f"{a}-{b}" for a, b in ERAS],
        "block_units": dict(DECLARED_UNIT),
        "block_unit_note": ("Book H is graded on MONTHLY blocks and Book I on "
                            "QUARTERLY ones, because `prstkc` is an annual "
                            "field. Every number on this receipt carries the "
                            "unit its own book earns, and the two may not be "
                            "compared without dividing I's by three."),
    }

    books = []
    quarters = sorted(qpanel["ym"].unique())
    months = sorted(panel["ym"].unique())

    try:
        grants = load_grants(start, end)
        daily = load_daily_cum(start, end)
        frames, covered, h_stats = build_book_h(grants, daily, months)
        pl_frames, pl_covered, pl_stats = build_book_h(
            grants, daily, months, placebo=True, seed=PLACEBO_SEED)
        h_stats["placebo"] = pl_stats
        # The daily tape and the grant table are the two biggest things this
        # job holds and neither is read again once the frames exist. Freed by
        # name rather than left to the interpreter, because the replay that
        # follows allocates a frame per month per cell and the model server
        # already holds most of this machine's RAM.
        del daily, grants
        gc.collect()
        books.append(replay_book_h(panel, frames, covered, pl_frames,
                                   pl_covered, smoke=smoke,
                                   panel_stats=h_stats))
        del frames, pl_frames, pl_covered
        gc.collect()
    except CharacteristicPanelUnavailable as exc:
        logger.warning("Book H refused: %s", exc)
        books.append({"book": "option_grant_timing_v0", "book_key": "H",
                      "prereg": "TRIAL-DRAFT-H", "ran": False,
                      "refused": str(exc)})

    try:
        i_frames, i_variants, i_covered, i_stats = build_book_i(
            start, end, quarters)
        books.append(replay_book_i(qpanel, i_frames, i_variants, i_covered,
                                   smoke=smoke, panel_stats=i_stats))
    except CharacteristicPanelUnavailable as exc:
        logger.warning("Book I refused: %s", exc)
        books.append({"book": "buyback_insider_divergence_v0", "book_key": "I",
                      "prereg": "TRIAL-DRAFT-I", "ran": False,
                      "refused": str(exc)})

    pvals = {name: None for name in DECLARED_FAMILY}
    for b in books:
        if b.get("ran"):
            pvals[b["book"]] = _p((b.get("cells") or {}).get("primary_floor"))
    family_holm = holm(pvals, family=FAMILY)
    family_holm["declared_before_either_read"] = (
        "The family was declared at size TWO in both drafts before either book "
        "was read. A leg that refused is NAMED here with a null p-value rather "
        "than dropped, because Holm over one p-value in a family that declared "
        "two is a different correction and a reader has to see which happened.")

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
        "next_test": ("Book J -- the survivor combination -- once at least one "
                      "of these carries a POSITIVE $10M cell; and for either "
                      "book, the TAQ cost curve in place of the flat ruler."),
        "verdict": ("SMOKE — proves the job runs end to end; no verdict is "
                    "read from a shortened window on the largest names"
                    if smoke else
                    "read each book against its own pre-registration's "
                    "decision rule, under the family Holm block above; both "
                    "floors are printed for every book or neither is"),
        "wall_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
    }


__all__ = ["B_books_hi_replay", "DECLARED_EFFECT", "DECLARED_FAMILY",
           "DECLARED_MDE", "DECLARED_UNIT", "FAMILY", "JOB", "K",
           "SECONDARY_FLOOR_USD", "book_h_selector", "book_i_selector",
           "build_book_h", "build_book_i", "classify_scheduled",
           "coverage_and_contamination", "decide_cell", "expand_pair_months",
           "grant_windows", "insider_dir", "load_buyback_rows",
           "daily_from_frame", "load_daily_cum", "load_grants",
           "load_sale_rows", "out_dir",
           "pair_state_rows", "recompute_mde", "replay_book_h",
           "replay_book_i", "run_cell", "sell_intensity", "to_quarterly"]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    print(json.dumps(B_books_hi_replay(smoke=a.smoke), indent=1, default=str))
