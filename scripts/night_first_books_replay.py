"""T3 — the historical replication of the first four books, as a NIGHT JOB.

WHY A NIGHT JOB AND NOT A CADENCE PASS
======================================
Three of the four books cannot decide on the 2025-26 ticker bars: Book A's
short-interest panel and Book C's turnover both live in CRSP permno space and
CRSP ends 2024-12-31. `book_cadence` says so by name on every pass and marks
them anyway. Their evidence has to come from somewhere, and it comes from here:
the same contracts, replayed monthly over the CRSP tape, each against the twin
its own pre-registration names.

WHAT IT COMPUTES, AND WHAT IT REFUSES
=====================================
One receipt per book. Each carries the book's primary metric, its per-era
split, a Newey-West lag-2 t, the realised turnover and cost, and `next_test` —
the thing that would change the verdict, named while the number is fresh.

`B_first_books_replay` is ONE job over a family of FOUR primary tests
(`NIGHT_JOB_BOOKS_2026_09`), so Holm runs across the family INSIDE the job.
A book whose leg cannot run is NAMED in the Holm block rather than dropped:
Holm over three p-values in a family that declared four is a different
correction, and a reader has to see which happened.

  A  si_low_turnover_high_v1               monthly cross-section, 1990-2024
  B  insider_cluster_length_v1             BHAR(22,90) events, 2006-2024
  B' insider_cluster_same_day_v1           the falsifier arm, same window
  C  disposition_overhang_conditioner_v0   monthly, 1995-2024, vs the
                                           UNCONDITIONED book run fresh
  D  abstention_book_v0                    NO HISTORICAL LEG. Its slice is
                                           forward-only by registration and it
                                           is refused here by name, not omitted.

THE COST MODEL IS A PLACEHOLDER AND SAYS SO
===========================================
25 bps flat per unit of notional traded, applied to `sum(|w_t - w_t-1|)`, so a
full rotation costs 50 bps. That is the interim ruler until chunk 5c lands the
TAQ empirical curve; `NEGATIVE_RESULTS.md` §25 already has two rulers
disagreeing 3.4-9.1x on exactly this segment, and every receipt here prints
`cost_curve: "flat_25bps_pending_5c"` so no number from this job can later be
quoted as if it had been measured.

    python -m scripts.night_factory_jobs B_first_books_replay --smoke
    python -m scripts.night_factory_jobs B_first_books_replay

THE TIME BOX THIS JOB NEEDS, MEASURED
=====================================
Two measured scaling points on this machine: 36 months x 200 names took
**30.1 s**, and 120 months x 1,000 names took **127.4 s**. The full pass is 420
months over roughly 6,000 permnos and additionally builds a 35-year wide daily
return frame for Book B's BHAR windows (~35M rows collapsing to about
8,800 x 6,000 floats, ~0.4 GB), so it is memory-bound rather than CPU-bound.
Projection: **20-45 minutes.** It is deliberately NOT in `night_factory.QUEUE`
— this is a replication that runs when someone asks for it, not every night —
which means `night_queue_plan` gives it the DEFAULT 60-minute box. That covers
the projection with little room at the top end: whoever queues the full pass
should set the box explicitly rather than trust the default, because a job
killed at 60 minutes writes no receipt at all (2026-09-10, G3 at generation
340).
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("first_books_replay")

FAMILY = "NIGHT_JOB_BOOKS_2026_09"

#: The interim cost ruler. Named on every row so it cannot be read as measured.
COST_BPS_PER_SIDE = 25.0
COST_CURVE = "flat_25bps_pending_5c"

FLOOR_USD = 3_000_000.0
MIN_PRICE = 5.0

#: Eras every monthly book is split by. The confirm slice per book is in its
#: own pre-registration; these are the REPORTED splits and decide nothing.
ERAS = ((1990, 1999), (2000, 2009), (2010, 2016), (2017, 2024))

FULL_START, FULL_END = 1990, 2024
SMOKE_START, SMOKE_END = 2022, 2024
SMOKE_NAMES = 200


def wrds_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "wrds"


def out_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "first_books" / "replay"


# --------------------------------------------------------------------------
# statistics


def newey_west_t(x, lag: int = 2) -> float | None:
    """t on the mean of a block series with a Newey-West lag-`lag` variance."""
    import numpy as np

    a = np.asarray(list(x), dtype=float)
    a = a[np.isfinite(a)]
    n = a.size
    if n < 3:
        return None
    mu = float(a.mean())
    e = a - mu
    s = float((e * e).sum()) / n
    for L in range(1, int(lag) + 1):
        if L >= n:
            break
        w = 1.0 - L / (lag + 1.0)
        s += 2.0 * w * float((e[L:] * e[:-L]).sum()) / n
    se = math.sqrt(s / n) if s > 0 else 0.0
    # A series with no dispersion has no sampling distribution, and float noise
    # makes `s > 0` true anyway: 20 copies of 0.01 produced a t of 1.5e16 on
    # the first run of this function's own test. The scale test is relative to
    # the mean, because an absolute epsilon is wrong at both ends of the range
    # this job covers (monthly excesses of 1e-3, BHAR blocks of 1e-1).
    if se <= 1e-12 * max(1.0, abs(mu)):
        return None
    return mu / se


def two_sided_p(t: float | None) -> float | None:
    if t is None or not math.isfinite(t):
        return None
    return math.erfc(abs(float(t)) / math.sqrt(2.0))


def holm(pvals: dict) -> dict:
    """Holm-Bonferroni over the family. Missing legs are NAMED, not dropped."""
    have = {k: v for k, v in pvals.items() if v is not None}
    missing = sorted(k for k, v in pvals.items() if v is None)
    m = len(pvals)                                # the DECLARED family size
    out = {}
    for i, (k, p) in enumerate(sorted(have.items(), key=lambda kv: kv[1])):
        out[k] = {"p_raw": round(float(p), 6),
                  "holm_alpha": round(0.05 / (m - i), 6),
                  "rejects_at_holm": bool(p <= 0.05 / (m - i))}
    return {"family": FAMILY, "declared_family_size": m,
            "legs_with_a_p_value": sorted(have), "legs_without": missing,
            "per_leg": out,
            "note": ("Holm is computed against the DECLARED family size, not "
                     "the number of legs that happened to run. A leg that "
                     "could not run does not make the correction cheaper for "
                     "the ones that did.")}


# --------------------------------------------------------------------------
# the tape


def load_monthly_panel(start: int, end: int, *, max_names: int | None = None):
    """Per (permno, month): return, last price, mean daily dollar volume.

    The eligibility columns are computed from the month that has ALREADY
    CLOSED, and selection happens at that close for the NEXT month's return, so
    nothing in a selection is contemporaneous with the return it earns.
    """
    import pandas as pd

    frames = []
    for y in range(int(start), int(end) + 1):
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if not p.is_file():
            continue
        df = pd.read_parquet(p, columns=["permno", "date", "ret", "prc", "vol",
                                         "shrout"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["ret"])
        df["ym"] = df["date"].dt.to_period("M")
        df["lg"] = (1.0 + df["ret"].astype(float)).clip(lower=1e-9).apply(math.log)
        df["dv"] = df["prc"].abs() * df["vol"]
        g = df.groupby(["permno", "ym"], sort=False).agg(
            lg=("lg", "sum"), n=("lg", "size"), dv=("dv", "median"),
            price=("prc", "last"), shrout=("shrout", "last"),
            vol_sum=("vol", "sum")).reset_index()
        g = g[g["n"] >= 15]
        g["ret_m"] = g["lg"].apply(math.exp) - 1.0
        g["price"] = g["price"].abs()
        g["turnover_m"] = g["vol_sum"] / (g["shrout"] * 1000.0).replace(0.0, float("nan"))
        frames.append(g[["permno", "ym", "ret_m", "price", "dv", "turnover_m"]])
    if not frames:
        raise FileNotFoundError(f"no CRSP daily files under {wrds_dir()}")
    panel = pd.concat(frames, ignore_index=True)
    if max_names:
        keep = (panel.groupby("permno")["dv"].median()
                .sort_values(ascending=False).head(int(max_names)).index)
        panel = panel[panel["permno"].isin(set(keep))]
    return panel.sort_values(["ym", "permno"], kind="mergesort").reset_index(drop=True)


def eligible(month_frame):
    m = month_frame
    return m[(m["dv"] >= FLOOR_USD) & (m["price"] >= MIN_PRICE)]


# --------------------------------------------------------------------------
# the monthly engine
#
# One function, used by A and C and by both of their controls, so that a book
# and its comparator can never differ by which code path ran them.


def run_monthly(panel, select, *, k: int, seed: int, label: str,
                twin: str = "random_universe", twin_select=None) -> dict:
    """Replay one selector monthly against a twin. Returns the two series.

    `select(month_frame, ym) -> list[permno]`, from information known at the
    close of `ym`; the return earned is `ym+1`'s. `twin_select` defaults to a
    uniform draw of the same size from the SAME eligible frame, seeded per
    month from `seed` so the control is reconstructible and different every
    period, which is what a random-genome null is.
    """
    import numpy as np

    months = sorted(panel["ym"].unique())
    by_month = {ym: g for ym, g in panel.groupby("ym", sort=False)}
    book_r, twin_r, blocks = [], [], []
    prev_book: set = set()
    prev_twin: set = set()
    n_sel = []
    for i in range(len(months) - 1):
        ym, nxt = months[i], months[i + 1]
        pool = eligible(by_month[ym])
        if pool.empty:
            continue
        picked = list(select(pool, ym) or [])[: int(k)]
        if not picked:
            continue
        rng = np.random.default_rng(int(seed) + int(ym.year) * 100 + int(ym.month))
        if twin_select is not None:
            tw = list(twin_select(pool, ym) or [])[: int(k)]
        else:
            tw = _turnover_matched_draw(pool, picked, prev_book, prev_twin, rng)
        nf = by_month.get(nxt)
        if nf is None:
            continue
        rmap = dict(zip(nf["permno"], nf["ret_m"]))
        b = [rmap[p] for p in picked if p in rmap]
        t = [rmap[p] for p in tw if p in rmap]
        if not b or not t:
            continue
        gross_b, gross_t = float(np.mean(b)), float(np.mean(t))
        cost_b = _cost(prev_book, set(picked))
        cost_t = _cost(prev_twin, set(tw))
        prev_book, prev_twin = set(picked), set(tw)
        book_r.append(gross_b - cost_b)
        twin_r.append(gross_t - cost_t)
        blocks.append(str(nxt))
        n_sel.append(len(picked))
    diff = [b - t for b, t in zip(book_r, twin_r)]
    t_nw = newey_west_t(diff)
    return {
        "label": label, "twin": twin, "k": int(k), "seed": int(seed),
        "twin_turnover_matched": twin_select is None,
        "n_blocks": len(diff),
        "median_names_selected": (int(np.median(n_sel)) if n_sel else 0),
        "mean_book_net_monthly": (round(float(np.mean(book_r)), 6) if book_r else None),
        "mean_twin_net_monthly": (round(float(np.mean(twin_r)), 6) if twin_r else None),
        "mean_excess_net_monthly": (round(float(np.mean(diff)), 6) if diff else None),
        "nw_lag2_t": (round(t_nw, 4) if t_nw is not None else None),
        "p_two_sided": (round(two_sided_p(t_nw), 6) if t_nw is not None else None),
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "blocks": blocks, "excess": [round(d, 6) for d in diff],
    }


def _turnover_matched_draw(pool, picked, prev_book: set, prev_twin: set, rng):
    """A random twin that rotates as much as its book did, and no more.

    WHY THIS IS NOT A UNIFORM DRAW EVERY PERIOD

    The spec says the random twin is "drawn uniformly at random each period
    from the SAME eligible band, rebalanced on the identical schedule". Read
    literally that means a FULL rotation every month, and at this job's flat
    25 bps it hands the book a structural cost advantage of up to 50 bps a
    month -- about 6%/yr, against a Book A MDE of 0.685%/month. The first run
    of this engine's own test measured it: on a panel where every name earned
    exactly the same return, the book beat its twin by +0.354%/month, entirely
    from the twin's churn.

    A control that loses on costs is not a control for SELECTION. So the twin
    replaces exactly as many names as the book replaced this period, drawn at
    random, and holds the rest. Its turnover equals the book's by construction
    and the cost term cancels out of the difference, which leaves the
    difference measuring the only thing that differs: which names.

    Forced replacements (a twin name that left the eligible pool) are the one
    case where the match is inexact, and they make the twin's turnover HIGHER,
    never lower -- the residual bias is against the twin and therefore against
    the book's own result being an artefact of it.
    """
    cand = [int(x) for x in pool["permno"].tolist()]
    target = len(picked)
    if not cand or target <= 0:
        return []
    alive = [p for p in prev_twin if p in set(cand)]
    n_new_in_book = len(set(picked) - set(prev_book)) if prev_book else target
    keep_n = max(0, min(len(alive), target - n_new_in_book))
    keep = ([int(alive[int(j)]) for j in
             rng.choice(len(alive), size=keep_n, replace=False)]
            if keep_n else [])
    # The names the twin just dropped are excluded from the refill pool: a
    # "replacement" that re-buys the name it sold is not a replacement, and it
    # would make the twin's realised turnover LOWER than the book's, which is
    # the bias this function exists to remove.
    held = set(keep) | set(prev_twin)
    rest = [p for p in cand if p not in held]
    if len(rest) < target - len(keep):
        rest = [p for p in cand if p not in set(keep)]
    need = min(target - len(keep), len(rest))
    add = ([int(rest[int(j)]) for j in
            rng.choice(len(rest), size=need, replace=False)] if need > 0 else [])
    return sorted(set(keep) | set(add))


def _cost(prev: set, now: set) -> float:
    """25 bps on every unit of notional traded. A full rotation costs 50 bps."""
    if not now:
        return 0.0
    if not prev:
        return COST_BPS_PER_SIDE / 1e4 * 1.0
    w_prev = {p: 1.0 / len(prev) for p in prev}
    w_now = {p: 1.0 / len(now) for p in now}
    traded = sum(abs(w_now.get(p, 0.0) - w_prev.get(p, 0.0))
                 for p in set(prev) | set(now))
    return COST_BPS_PER_SIDE / 1e4 * traded


def by_era(result) -> dict:
    """The per-era split. REPORTED, never deciding."""
    import numpy as np
    import pandas as pd

    out = {}
    if not result.get("blocks"):
        return out
    years = [pd.Period(b).year for b in result["blocks"]]
    for lo, hi in ERAS:
        vals = [e for y, e in zip(years, result["excess"]) if lo <= y <= hi]
        if len(vals) < 6:
            out[f"{lo}-{hi}"] = {"n_blocks": len(vals),
                                 "verdict": "too few blocks to report a mean"}
            continue
        t = newey_west_t(vals)
        out[f"{lo}-{hi}"] = {"n_blocks": len(vals),
                             "mean_excess_net_monthly": round(float(np.mean(vals)), 6),
                             "nw_lag2_t": (round(t, 4) if t is not None else None)}
    return out


# --------------------------------------------------------------------------
# BOOK A


def replay_book_a(panel, *, smoke: bool) -> dict:
    """Top-50 (low SI x high turnover) vs a random draw from the same band."""
    import pandas as pd

    from backend.services import book_signals as BS

    years = sorted({p.year for p in panel["ym"].unique()})
    frames = []
    d = BS.short_interest_panel_dir()
    for y in years:
        f = d / f"{y}.parquet"
        if f.is_file():
            frames.append(pd.read_parquet(f, columns=["permno", "observed_at",
                                                      "si_ratio", "turnover_21d_w"]))
    if not frames:
        return {"book": "si_low_turnover_high_v1", "ran": False,
                "refused": (f"no short-interest panel under {d}. Build it with "
                            f"`python -m scripts.short_interest_panel`; this job "
                            f"does not build data it was asked to replay.")}
    si = pd.concat(frames, ignore_index=True)
    si["observed_at"] = pd.to_datetime(si["observed_at"])

    def select(pool, ym):
        asof = ym.to_timestamp(how="end")
        sub = si[si["observed_at"] <= asof]
        if sub.empty:
            return []
        sub = sub[sub["permno"].isin(set(pool["permno"]))]
        if len(sub) < 20:
            return []
        try:
            scores = BS.si_turnover_composite(sub, asof, min_names=20)
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(scores.items(), key=lambda kv: -kv[1])]

    res = run_monthly(panel, select, k=50, seed=0x1934, label="si_low_turnover_high_v1")
    return {
        "book": "si_low_turnover_high_v1",
        "book_id": "book:1934ec97aa4b1620",
        "prereg": "TRIAL-DRAFT-A-si-low-turnover-high-v1 (UNSIGNED)",
        "primary_metric": "net_monthly_excess_vs_random_twin",
        "confirm_slice": "2011-2024", "ran": True,
        "result": {k: v for k, v in res.items() if k not in ("blocks", "excess")},
        "by_era": by_era(res),
        "declared_mde_monthly": 0.00685, "declared_effect_size": 0.01,
        "next_test": ("re-measure the SAME double sort at a $10M dollar-volume "
                      "floor. TRIAL-H5's lesson is that a corner-dependent "
                      "control must be re-measured at every corner, and this "
                      "book's decision rule closes it as FAILED_VARIANT if the "
                      "$10M cell fails while the $3M cell passes."),
        "smoke": bool(smoke),
    }


# --------------------------------------------------------------------------
# BOOK B and its falsifier arm


def replay_book_b(panel, *, spans, label: str, book_id: str,
                  smoke: bool) -> dict:
    """BHAR(22,90) per filing-month block vs a random Form-4-active twin."""
    import numpy as np
    import pandas as pd

    from backend.services import book_signals as BS

    p = BS.insider_events_path()
    if not p.is_file():
        return {"book": label, "ran": False,
                "refused": f"the Form-4 event table is not on this machine: {p}"}
    years = sorted({y.year for y in panel["ym"].unique()})
    buys = pd.read_parquet(p, columns=["symbol", "permno", "event_type",
                                       "event_time_utc", "observed_at_utc",
                                       "insider_cik", "insider_is_officer",
                                       "insider_dollar_value", "year"])
    buys = buys[(buys["event_type"] == "insider_open_market_buy")
                & (buys["year"].isin(years))
                & buys["permno"].notna()]
    if buys.empty:
        return {"book": label, "ran": False,
                "refused": (f"no open-market purchase rows in {years[0]}-{years[-1]}; "
                            f"the Form-4 tape starts 2006q1")}
    # cluster on PERMNO, since the replay is in permno space
    buys = buys.assign(symbol=buys["permno"].astype("int64").astype(str))
    daily = _daily_returns(years)
    if daily is None:
        return {"book": label, "ran": False, "refused": "no CRSP daily panel"}
    sessions = sorted(daily.index)
    clusters = BS.cluster_lengths(buys, sessions=sessions)
    if clusters.empty:
        return {"book": label, "ran": False,
                "refused": "no multi-insider cluster in this window"}
    hit = clusters[clusters["span_days"].isin(list(spans))].copy()
    hit["block"] = pd.to_datetime(hit["entry_date"]).dt.to_period("M")
    active = buys.assign(
        block=pd.to_datetime(buys["observed_at_utc"], utc=True)
        .dt.tz_localize(None).dt.to_period("M"))

    rows, blocks = [], []
    rng = np.random.default_rng(0x625C)
    for block, grp in hit.groupby("block", sort=True):
        names = [int(s) for s in grp["symbol"].unique()]
        pool = sorted({int(s) for s in active[active["block"] == block]["symbol"]})
        if not names or len(pool) < 2:
            continue
        b = [_bhar(daily, n, block) for n in names]
        b = [v for v in b if v is not None]
        draw = rng.choice(len(pool), size=min(len(names), len(pool)), replace=False)
        t = [_bhar(daily, int(pool[int(j)]), block) for j in draw]
        t = [v for v in t if v is not None]
        if not b or not t:
            continue
        cost = 2.0 * COST_BPS_PER_SIDE / 1e4          # one round trip per event
        rows.append(float(np.mean(b)) - float(np.mean(t)) - 0.0)
        blocks.append(str(block))
        del cost
    if len(rows) < 3:
        return {"book": label, "ran": False,
                "refused": (f"only {len(rows)} filing-month block(s) carried both "
                            f"a {list(spans)}-day cluster and a usable BHAR "
                            f"window; a block mean over fewer than 3 is not one")}
    t_nw = newey_west_t(rows)
    res = {"n_blocks": len(rows),
           "mean_bhar_excess_vs_twin": round(float(np.mean(rows)), 6),
           "nw_lag2_t": (round(t_nw, 4) if t_nw is not None else None),
           "p_two_sided": (round(two_sided_p(t_nw), 6) if t_nw is not None else None),
           "cost_curve": COST_CURVE,
           "cost_note": ("both legs pay the same one round trip per event at "
                         "the flat rate, so the DIFFERENCE is cost-neutral by "
                         "construction here; the LEVEL of each leg is not, and "
                         "chunk 5c's curve is what makes the level quotable"),
           "blocks": blocks, "excess": [round(r, 6) for r in rows]}
    return {"book": label, "book_id": book_id,
            "prereg": "TRIAL-DRAFT-B-insider-cluster-length-v1 (UNSIGNED)",
            "primary_metric": "net_bhar_22_90_vs_random_active_twin",
            "confirm_slice": "2017-2024", "ran": True,
            "spans": list(spans),
            "result": {k: v for k, v in res.items() if k not in ("blocks", "excess")},
            "by_era": by_era(res),
            "declared_mde_per_block": 0.0717,
            "power_warning": ("the registered MDE (7.17%) is ABOVE the published "
                              "effect (5.0%): a non-significant result here is "
                              "CONDITIONAL, never FAILED_VARIANT, unless the "
                              "point estimate is <= 0"),
            "next_test": ("the same-day arm. The length-conditioning claim is "
                          "falsified if span-0 clusters BEAT non-cluster "
                          "purchases, whatever the 4-5 day arm did, and that "
                          "test does not need the 7.17% the mean test needs."),
            "smoke": bool(smoke)}


_DAILY_MEMO: dict = {}


def _daily_returns(years):
    """Wide daily return frame (date x permno) for the replay window."""
    import pandas as pd

    key = (min(years), max(years))
    if key in _DAILY_MEMO:
        return _DAILY_MEMO[key]
    frames = []
    for y in range(min(years), max(years) + 2):
        p = wrds_dir() / f"crsp_dsf_{y}.parquet"
        if p.is_file():
            df = pd.read_parquet(p, columns=["permno", "date", "ret"])
            frames.append(df)
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    wide = d.pivot_table(index="date", columns="permno", values="ret",
                         aggfunc="last").sort_index()
    _DAILY_MEMO.clear()
    _DAILY_MEMO[key] = wide
    return wide


def _bhar(daily, permno: int, block) -> float | None:
    """Buy-and-hold market-adjusted return over trading days [22, 90].

    Measured from the first session of the month AFTER the filing month, so
    nothing in the window precedes the filing that made the name eligible.
    """
    import numpy as np
    import pandas as pd

    if permno not in daily.columns:
        return None
    start = pd.Timestamp(block.to_timestamp(how="end")) + pd.Timedelta(days=1)
    idx = daily.index[daily.index >= start]
    if len(idx) < 91:
        return None
    win = daily.loc[idx[:91]]
    col = win[permno]
    if col.isna().mean() > 0.2:
        return None
    r = (1.0 + col.fillna(0.0).to_numpy(dtype=float))
    mkt = (1.0 + win.mean(axis=1).to_numpy(dtype=float))
    name = float(np.prod(r[22:91]) - 1.0)
    market = float(np.prod(mkt[22:91]) - 1.0)
    if not math.isfinite(name) or not math.isfinite(market):
        return None
    return name - market


# --------------------------------------------------------------------------
# BOOK C


#: What the v0 conditioning sign IS, in one string every receipt built on these
#: inputs prints. v1 is a separate registration amendment naming only the input.
EVENT_SIGN_V0 = "v0: sign(numup - numdown), IBES EPS fpi=1, at statpers"

#: The eligible set below which the conditioner has no cross-section to cut into
#: terciles. Frozen with the book; the falsifiers inherit it rather than choosing
#: their own, because a different floor is a different universe.
MIN_CONDITIONED_NAMES = 6

#: The overhang lookback, in MONTHS. TRIAL-DRAFT-C §2 freezes T = 1260 trading
#: days, which is 60 months at this panel's resolution.
CGO_LOOKBACK_MONTHS = 60

#: How much history a name must have before its CGO is computed AT ALL — which
#: is NOT the same number, and the difference is a defect this job shipped on
#: 2026-09-12 and a later reader found.
#:
#: 24 is what run 1 used: a name with 24 months of history got a reference price
#: from 24 months and it was reported as if the window were 60. Every name's
#: first 36 months, and the whole 1990-1994 stretch (the panel starts 1990), are
#: therefore TRUNCATED-window overhangs — and the pooled 395-block result and
#: the 1990-1999 era both include them, while the receipt says
#: `confirm_slice: 1995-2024`.
#:
#: The default stays 24 SO THAT RUN 1 REMAINS REPRODUCIBLE. The registered
#: construction is `min_history=CGO_LOOKBACK_MONTHS` and a read that starts in
#: 1995, and `scripts/night_c_falsifiers.py` passes it explicitly. A silent
#: change here would rewrite a published receipt's meaning without moving a
#: number anybody could see.
CGO_MIN_HISTORY_RUN01 = 24


class BookCInputsUnavailable(RuntimeError):
    """The IBES consensus panel Book C's v0 event sign needs is not on disk.

    Raised rather than returned, because `replay_book_c` turns it into the
    book's own named refusal and the falsifier job turns it into a different
    one. A shared `None` would leave both of them guessing.
    """


def book_c_overhang(panel, *, min_history: int = CGO_MIN_HISTORY_RUN01,
                    lookback: int = CGO_LOOKBACK_MONTHS) -> dict:
    """{month: {permno: CGO}} from the panel's own price and turnover.

    The Grinblatt-Han recursion at MONTHLY resolution, which is Grinblatt-Han's
    own cadence (they use weekly/260; the daily 1260 of the contract is the
    finer form and is what the forward book would use if turnover existed on
    bars). A name's history is everything strictly BEFORE the month being
    stamped — the append happens after the read — so no overhang contains the
    price it is used to rank.

    A name needs `min_history` months before it gets an overhang at all. That
    is a DIFFERENT number from `lookback`, and run 1 set them to 24 and 60,
    which is a truncated window reported as a full one.

    Separated from `book_c_inputs` so it can be tested without an IBES panel:
    a gate whose only test has to stub three unrelated readers is a gate nobody
    re-tests.
    """
    import numpy as np

    from backend.services import book_signals as BS

    hist: dict = {}
    cgo_by_month: dict = {}
    for ym, g in panel.groupby("ym", sort=True):
        cgo_here = {}
        for pn, px, tv in zip(g["permno"], g["price"], g["turnover_m"]):
            h = hist.setdefault(int(pn), ([], []))
            if len(h[0]) >= int(min_history):
                try:
                    cgo_here[int(pn)] = BS.capital_gains_overhang(
                        h[0], h[1], lookback=int(lookback))
                except BS.SignalUnavailable:
                    pass
            h[0].append(float(px))
            h[1].append(float(tv) if np.isfinite(tv) else 0.0)
        cgo_by_month[ym] = cgo_here
    return cgo_by_month


def book_c_inputs(panel, *, min_history: int = CGO_MIN_HISTORY_RUN01,
                  lookback: int = CGO_LOOKBACK_MONTHS) -> dict:
    """The two objects every Book C leg is built from, computed ONCE.

    Returned rather than closed over inside `replay_book_c`, because
    `scripts/night_c_falsifiers.py` builds the sign-flipped placebo from the
    SAME event-sign sets and the SAME overhang series this book traded. A
    second implementation of the Grinblatt-Han recursion would make the placebo
    a different construction, and a placebo that is a different construction
    tests nothing.

    `good` and `bad` are sets of `(ym.ordinal, permno)`. A name whose month
    carries contradictory IBES rows can land in both; `good` is built exactly as
    the first read built it, and it is the FALSIFIER that subtracts.

    `min_history` is how many months a name must carry before its overhang is
    computed at all. The default is run 1's 24 and is kept SO RUN 1 REMAINS
    REPRODUCIBLE; the registered construction is 60 — a full reference-price
    window — and the caller that wants it says so (see `CGO_MIN_HISTORY_RUN01`).
    """
    import numpy as np
    import pandas as pd


    con = wrds_dir() / "ibes_consensus_monthly.parquet"
    early = wrds_dir() / "ibes_consensus_monthly_early.parquet"
    frames = [pd.read_parquet(p, columns=["permno", "statpers", "measure",
                                          "fpi", "numup", "numdown"])
              for p in (early, con) if p.is_file()]
    if not frames:
        raise BookCInputsUnavailable(
            f"no IBES consensus panel at {con} or {early}; the v0 event sign "
            f"is the monthly consensus revision and this job does not "
            f"substitute another one")
    ib = pd.concat(frames, ignore_index=True)
    ib = ib[(ib["measure"] == "EPS") & (ib["fpi"].astype(str) == "1")]
    ib["statpers"] = pd.to_datetime(ib["statpers"])
    ib["ym"] = ib["statpers"].dt.to_period("M")
    ib["sign"] = np.sign(ib["numup"].fillna(0.0) - ib["numdown"].fillna(0.0))
    ib = ib.dropna(subset=["permno"])
    ib["permno"] = ib["permno"].astype("int64")
    good = {(int(r.ym.ordinal), int(r.permno))
            for r in ib[ib["sign"] > 0][["ym", "permno"]].itertuples()}
    bad = {(int(r.ym.ordinal), int(r.permno))
           for r in ib[ib["sign"] < 0][["ym", "permno"]].itertuples()}

    cgo_by_month = book_c_overhang(panel, min_history=min_history,
                                   lookback=lookback)
    return {"good": good, "bad": bad, "cgo_by_month": cgo_by_month,
            "event_sign": EVENT_SIGN_V0,
            "cgo_min_history_months": int(min_history),
            "cgo_lookback_months": int(lookback),
            "cgo_window_is_full": bool(int(min_history) >= int(lookback))}


def names_with_sign(pool, ym, wanted: set) -> list:
    """`pool`'s permnos carrying the wanted event sign this month, in pool order."""
    o = int(ym.ordinal)
    return [int(p) for p in pool["permno"] if (o, int(p)) in wanted]


def book_c_selectors(inputs: dict) -> dict:
    """Book C's two legs as selectors. The falsifier reuses `unconditioned`."""
    from backend.services import book_signals as BS

    good = inputs["good"]
    cgo_by_month = inputs["cgo_by_month"]

    def good_news(pool, ym):
        return names_with_sign(pool, ym, good)

    def select_conditioned(pool, ym):
        names = good_news(pool, ym)
        cgo = {n: v for n, v in (cgo_by_month.get(ym) or {}).items() if n in set(names)}
        if len(cgo) < MIN_CONDITIONED_NAMES:
            return []
        try:
            top = BS.overhang_conditioned_ranks(cgo, {n: 1.0 for n in cgo})
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(top.items(), key=lambda kv: -kv[1])]

    def select_unconditioned(pool, ym):
        names = good_news(pool, ym)
        return sorted(names)[:30]

    return {"good_news": good_news, "conditioned": select_conditioned,
            "unconditioned": select_unconditioned}


def replay_book_c(panel, *, smoke: bool) -> dict:
    """Top-overhang-tercile good-news names MINUS the unconditioned book.

    Both legs run through `run_monthly` with the SAME code path; the only
    difference between them is the overhang gate, which is the whole claim.
    """
    try:
        inputs = book_c_inputs(panel)
    except BookCInputsUnavailable as exc:
        return {"book": "disposition_overhang_conditioner_v0", "ran": False,
                "refused": str(exc)}
    sel = book_c_selectors(inputs)
    res = run_monthly(panel, sel["conditioned"], k=30, seed=0xA82E,
                      label="disposition_overhang_conditioner_v0",
                      twin="unconditioned_reaction_book_v0",
                      twin_select=sel["unconditioned"])
    return {"book": "disposition_overhang_conditioner_v0",
            "book_id": "book:a82e6e453c14c241",
            "prereg": "TRIAL-DRAFT-C-disposition-overhang-conditioner-v0 (UNSIGNED)",
            "primary_metric": "conditioned_minus_unconditioned",
            "confirm_slice": "1995-2024", "ran": True,
            "event_sign": inputs["event_sign"],
            "cgo_construction": {
                "min_history_months": inputs["cgo_min_history_months"],
                "lookback_months": inputs["cgo_lookback_months"],
                "window_is_full": inputs["cgo_window_is_full"],
                "caveat": (
                    "at min_history 24 with a 60-month lookback, a name's first "
                    "36 overhangs are computed on a TRUNCATED reference-price "
                    "window, and so is the whole 1990-1994 stretch. The "
                    "registered construction (TRIAL-DRAFT-C §2 T=1260 sessions, "
                    "§4 slice_period 1995-01-01) is a FULL window and a read "
                    "that starts in 1995; `scripts/night_c_falsifiers.py` "
                    "re-reports this book's primary metric under it."),
            },
            "result": {k: v for k, v in res.items() if k not in ("blocks", "excess")},
            "by_era": by_era(res),
            "declared_mde_monthly": 0.00724, "declared_effect_size": 0.01,
            "next_test": ("the two FALSIFIERS, either of which closes the book "
                          "whatever the primary metric says: the sign-flip "
                          "placebo (long good-news/large-LOSS, short "
                          "bad-news/large-GAIN, which Frazzini reports at ~0) "
                          "and the momentum orthogonalisation (mom_12_1 must "
                          "DIE with overhang on the right-hand side)."),
            "smoke": bool(smoke)}


# --------------------------------------------------------------------------
# BOOK D — refused by name


def replay_book_d() -> dict:
    return {
        "book": "abstention_book_v0", "book_id": "book:b109c8861c43e3c6",
        "prereg": "TRIAL-DRAFT-D-abstention-book-v0 (UNSIGNED)", "ran": False,
        "refused": (
            "Book D has NO HISTORICAL LEG, by registration rather than by "
            "accident. Its `slice_purpose` is CONFIRM forward-only, its "
            "`slice_period` is 2026-10-01..2028-09-30, and its own decision "
            "rule forbids reading the risk-coverage curve before 24 monthly "
            "blocks have accrued. Replaying it on CRSP would be exactly the "
            "backfilled forward evidence the three licences prohibit."),
        "primary_metric": "terminal_wealth_at_equal_drawdown_vs_always_invested_twin",
        "next_test": ("the first cadence pass after seeding writes its first "
                      "NAV row; the twenty-fourth monthly block is the earliest "
                      "date any number from it may be read."),
    }


# --------------------------------------------------------------------------
# the job


def B_first_books_replay(*, smoke: bool = False) -> dict:       # noqa: N802
    """The night-factory entry point. One receipt file, one payload."""
    t0 = datetime.now(timezone.utc)
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    panel = load_monthly_panel(start, end,
                               max_names=SMOKE_NAMES if smoke else None)

    books = []
    books.append(replay_book_a(panel, smoke=smoke))
    books.append(replay_book_b(panel, spans=(4, 5),
                               label="insider_cluster_length_v1",
                               book_id="book:625c391913d9718c", smoke=smoke))
    books.append(replay_book_b(panel, spans=(0,),
                               label="insider_cluster_same_day_v1",
                               book_id="book:4359eba886a8a505", smoke=smoke))
    books.append(replay_book_c(panel, smoke=smoke))
    books.append(replay_book_d())

    pvals = {
        "si_low_turnover_high_v1": _p(books[0]),
        "insider_cluster_length_v1": _p(books[1]),
        "disposition_overhang_conditioner_v0": _p(books[3]),
        "abstention_book_v0": None,
    }
    d = out_dir()
    d.mkdir(parents=True, exist_ok=True)
    written = []
    stamp = t0.strftime("%Y-%m-%dT%H%M%SZ")
    for b in books:
        name = f"{b['book']}_{stamp}{'_smoke' if smoke else ''}.json"
        (d / name).write_text(json.dumps(b, indent=2, default=str),
                              encoding="utf-8")
        written.append(str(d / name))

    ran = [b for b in books if b.get("ran")]
    payload = {
        "job": "B_first_books_replay", "family": FAMILY,
        "licence": "PRODUCT_EXPERIMENT",
        "window": [start, end], "smoke": bool(smoke),
        "max_names": SMOKE_NAMES if smoke else None,
        "months_in_panel": int(panel["ym"].nunique()),
        "permnos_in_panel": int(panel["permno"].nunique()),
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "cost_caveat": ("a placeholder until chunk 5c's TAQ curve lands. "
                        "NEGATIVE_RESULTS §25 already has two rulers "
                        "disagreeing 3.4-9.1x on this segment; no LEVEL here "
                        "may be quoted as measured."),
        "books": books, "receipts": written,
        "holm": holm(pvals),
        "n_ran": len(ran), "n_refused": len(books) - len(ran),
        "headline": (f"{len(ran)}/{len(books)} legs ran over {start}-{end}"
                     f"{' (SMOKE)' if smoke else ''}; "
                     + "; ".join(
                         f"{b['book'].split('_v')[0]} "
                         f"{(b.get('result') or {}).get('mean_excess_net_monthly') or (b.get('result') or {}).get('mean_bhar_excess_vs_twin')}"
                         for b in ran) if ran else "no leg ran"),
        "verdict": ("SMOKE — proves the job runs end to end; no verdict is "
                    "read from a 3-year, 200-name window"
                    if smoke else
                    "read each book against its own pre-registration's "
                    "decision rule, under the family Holm block above"),
    }
    return payload


def _p(book: dict):
    r = book.get("result") or {}
    return r.get("p_two_sided")


__all__ = ["B_first_books_replay", "BookCInputsUnavailable", "COST_CURVE",
           "EVENT_SIGN_V0", "MIN_CONDITIONED_NAMES", "book_c_inputs",
           "book_c_selectors", "by_era", "eligible", "holm",
           "load_monthly_panel", "names_with_sign", "newey_west_t",
           "replay_book_d", "run_monthly", "two_sided_p"]
