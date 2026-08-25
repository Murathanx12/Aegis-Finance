"""Does expected return move monotonically with the signal? Ask BEFORE top-k.

WHY THIS EXISTS
===============
Every farm result to 2026-08-25 was produced by one chain:

    characteristic -> rank -> top-k long-only book -> compare to a benchmark

and then read as a statement about the CHARACTERISTIC. It is not one. That
chain entangles four things, and when the answer disappoints, nothing in the
output says which of them ate it:

    1. signal quality          — does forward return move with the score?
    2. portfolio construction  — does top-10-of-500 capture it, or destroy it?
    3. factor exposure         — is the book long size/age/sector by accident?
    4. benchmark choice        — better than WHAT?

Point 4 already cost this project five months (`portfolio_farm_paired_power`,
2026-08-25: the cap-weighted market said `profit_roe` was four months from
resolvable; an age-matched book said 126 years). This module is points 1-3.

WHAT IT WOULD HAVE CAUGHT
=========================
`value_bm` reads as a failure on the farm leaderboard. It is not: value is not
normally implemented as *"buy the ten highest book-to-market names among 500
mega-liquid stocks"*, and that book is a distress portfolio — AIG, Citigroup,
MetLife, US Steel, Whiting, Marathon. The finding is **extreme top-k value in
this universe selects distress**, which is a fact about construction. A decile
curve says that immediately and a top-k terminal wealth never says it at all.

`liquid` is the mirror image: best t on the 2013-2024 grid, and the holdings
census showed a static FAANG list (MSFT in 123 of 124 samples). A monotonicity
check and a turnover number would both have flagged it before the terminal
wealth was ever quoted.

WHAT IS AND IS NOT PIT HERE
===========================
The forward returns, the eligibility and the signal values are all
point-in-time and use the replay's own conventions — `replay.eligible_at` is
imported rather than reimplemented, and the entry is the NEXT OPEN exactly as
`replay` fills.

The DESCRIPTIVE exposures are not, and they are labelled. `permno_pct` uses
the permno ordering, which is fixed for all time; `panel_age_sessions` is
censored at the panel's left edge and says so in its own key name. Neither is
used to compute a return — they describe what a book held, which is a question
about the past by construction.

THE OVERLAP RULE
================
Formation rows are spaced `holding_days` apart, so consecutive forward returns
do not share a session and the IC t-statistic counts DATE BLOCKS rather than
days (canon §58). A rank IC computed on every session with a 21-day forward
return has ~21x the apparent sample and the same information; that inflation is
how a signal with no edge acquires a t of 4.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

#: Buckets for the monotonicity check. Five, not ten: the farm's universe is
#: `universe_n=500` and a decile of 500 is 50 names, which is a real portfolio;
#: a decile of a thin early-era date would not be.
DEFAULT_QUANTILES = 5

#: Sessions per year, for annualising a per-period spread.
YEAR_SESSIONS = 252

#: An IC date needs at least this many eligible, finite-signal names for its
#: cross-sectional correlation to mean anything.
MIN_NAMES_PER_DATE = 30


def open_total_return_index(panel) -> np.ndarray:
    """(T, N) total-return index measured at the OPEN, base-aligned to `tri`.

    The replay enters at the next open and exits at an open, so a signal
    diagnostic that scores close-to-close is scoring a convention the book
    cannot trade. But `tri` is close-based and is the only thing carrying
    dividends, so neither raw series is right on its own.

    This applies the overnight PRICE move to the previous close's total-return
    index:  `tri_open[t] = tri[t-1] * open_[t] / close[t-1]`.

    Dividends inside the holding period are captured by `tri`; the entry and
    exit points are the ones `replay` actually fills at. Omitting dividends
    instead would not be a wash for a cross-sectional test — dividend yield is
    strongly correlated with value and profitability, which are precisely the
    signals this module was built to judge.
    """
    tri = panel.tri.astype(np.float64)
    close = panel.close.astype(np.float64)
    open_ = panel.open_.astype(np.float64)
    out = np.full_like(tri, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        prev_close = np.where(close[:-1] > 0, close[:-1], np.nan)
        out[1:] = tri[:-1] * (open_[1:] / prev_close)
    return out


def formation_rows(panel, holding_days: int, warmup: int,
                   phase_offset: int = 0) -> np.ndarray:
    """Decision rows, spaced so consecutive forward returns never overlap.

    Mirrors `replay`'s own schedule: `first = warmup + phase_offset %
    holding_days`, then every `holding_days` sessions. The last row is dropped
    when its forward window would run past the panel — a truncated holding
    period is a different strategy, not a shorter sample.
    """
    T = panel.close.shape[0]
    first = int(warmup) + (int(phase_offset) % int(holding_days))
    rows = np.arange(first, T - 1, int(holding_days), dtype=int)
    # entry at r+1, exit at r+1+holding_days: both must exist
    return rows[rows + 1 + int(holding_days) <= T - 1]


def forward_returns(panel, rows: np.ndarray, holding_days: int,
                    tri_open: np.ndarray | None = None) -> np.ndarray:
    """(len(rows), N) total return from the next open to the open H later."""
    t = open_total_return_index(panel) if tri_open is None else tri_open
    entry = t[rows + 1]
    exit_ = t[rows + 1 + int(holding_days)]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(entry > 0, exit_ / entry - 1.0, np.nan)


def _rankdata(x: np.ndarray) -> np.ndarray:
    """Average-tie ranks of a 1-D finite array. Local, to avoid a scipy import
    in a module that runs inside sweeps."""
    order = np.argsort(x, kind="stable")
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.arange(1, len(x) + 1, dtype=np.float64)
    # average ties so a signal with many equal scores is not given a spurious
    # ordering — which is the `equal`/tie-break defect one level down
    _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
    if (counts > 1).any():
        sums = np.zeros(len(counts), dtype=np.float64)
        np.add.at(sums, inv, ranks)
        ranks = (sums / counts)[inv]
    return ranks


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra, rb = _rankdata(a), _rankdata(b)
    ra -= ra.mean()
    rb -= rb.mean()
    d = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    return float((ra * rb).sum() / d) if d > 0 else float("nan")


def rank_ic(sig: np.ndarray, fwd: np.ndarray, elig: np.ndarray,
            min_names: int = MIN_NAMES_PER_DATE) -> dict:
    """Cross-sectional Spearman of signal vs forward return, date by date.

    The headline is `ic_t`: mean IC divided by its own standard error across
    NON-OVERLAPPING dates. This is the first question to ask of a signal and
    the farm has never asked it — every leaderboard it printed went straight to
    terminal wealth, which answers "did this book do well" and not "does the
    score order returns".
    """
    ics, ns = [], []
    for r in range(sig.shape[0]):
        m = elig[r] & np.isfinite(sig[r]) & np.isfinite(fwd[r])
        n = int(m.sum())
        if n < min_names:
            continue
        ics.append(_spearman(sig[r][m], fwd[r][m]))
        ns.append(n)
    ics = np.asarray([x for x in ics if np.isfinite(x)], dtype=np.float64)
    if len(ics) < 3:
        return {"n_dates": int(len(ics)), "ic_mean": None, "ic_std": None,
                "ic_t": None, "ic_ir": None, "hit_rate_pct": None,
                "mean_names_per_date": None,
                "note": "too few usable dates for an IC"}
    sd = float(ics.std(ddof=1))
    mean = float(ics.mean())
    return {
        "n_dates": int(len(ics)),
        "ic_mean": round(mean, 5),
        "ic_std": round(sd, 5),
        # t over DATE BLOCKS, not days — see the module docstring
        "ic_t": round(mean / (sd / np.sqrt(len(ics))), 3) if sd > 0 else None,
        "ic_ir": round(mean / sd, 3) if sd > 0 else None,
        "hit_rate_pct": round(100.0 * float((ics > 0).mean()), 1),
        "mean_names_per_date": round(float(np.mean(ns)), 1),
    }


def quantile_profile(sig: np.ndarray, fwd: np.ndarray, elig: np.ndarray,
                     n_q: int = DEFAULT_QUANTILES, holding_days: int = 21,
                     min_names: int = MIN_NAMES_PER_DATE) -> dict:
    """Mean forward return by signal bucket, and whether it is MONOTONE.

    A signal whose top bucket wins while its middle buckets are unordered is
    not a signal with an edge at the top — it is far more often a handful of
    names, which is what `liquid` turned out to be. Monotonicity is the cheap
    test that separates the two, and it is a property of the whole cross
    section rather than of the tail a top-k book happens to buy.
    """
    per_q = [[] for _ in range(n_q)]
    used = 0
    for r in range(sig.shape[0]):
        m = elig[r] & np.isfinite(sig[r]) & np.isfinite(fwd[r])
        if int(m.sum()) < max(min_names, n_q * 5):
            continue
        used += 1
        s, f = sig[r][m], fwd[r][m]
        order = np.argsort(s, kind="stable")
        buckets = np.array_split(order, n_q)
        for q, b in enumerate(buckets):
            per_q[q].append(float(np.mean(f[b])))
    if used < 3:
        return {"n_dates": used, "note": "too few usable dates for quantiles"}

    means = np.array([np.mean(v) if v else np.nan for v in per_q])
    periods_per_year = YEAR_SESSIONS / float(holding_days)
    ann = (np.power(1.0 + means, periods_per_year) - 1.0) * 100.0
    lo, hi = means[0], means[-1]
    spread_ann = (np.power(1.0 + (hi - lo), periods_per_year) - 1.0) * 100.0

    # Spearman of bucket index against bucket mean: +1 is perfectly increasing.
    mono = _spearman(np.arange(n_q, dtype=np.float64), means)
    tb = np.array([np.array(per_q[-1]) - np.array(per_q[0])]).ravel()
    tb_t = (float(tb.mean()) / (float(tb.std(ddof=1)) / np.sqrt(len(tb)))
            if len(tb) > 2 and tb.std(ddof=1) > 0 else None)
    return {
        "n_dates": used,
        "n_quantiles": n_q,
        # q1 is the LOWEST signal score, qN the highest — the direction a
        # top-k book buys
        "mean_return_pct_by_quantile": [round(float(x) * 100, 4) for x in means],
        "annualised_pct_by_quantile": [round(float(x), 2) for x in ann],
        "top_minus_bottom_annual_pct": round(float(spread_ann), 2),
        "top_minus_bottom_t": round(tb_t, 3) if tb_t is not None else None,
        "monotonicity_spearman": round(float(mono), 3),
        # The bar is deliberately not 1.0: real signals are noisy at the
        # bucket level. It is high enough that "one bucket did everything"
        # fails it — which is what it is for, and it is ALL it is for.
        #
        # ON ITS OWN THIS IS A WEAK BAR AND SHOULD NEVER BE QUOTED ALONE. With
        # five buckets there are only a handful of attainable Spearman values,
        # and P(rho >= 0.6) under no relationship is roughly 14%. It earns its
        # keep only beside `ic_t`, where it separates "orders the whole cross
        # section" from "one bucket carried it" — the distinction that would
        # have caught `rev_dispersion` on 2013-2024 (ic_t 2.11, mono 0.10).
        "is_monotone": bool(np.isfinite(mono) and mono >= 0.6),
    }


def selection_census(panel, sig: np.ndarray, rows: np.ndarray,
                     elig: np.ndarray, top_k: int, n_report: int = 12) -> dict:
    """WHAT DID IT BUY. Names, concentration, turnover, age and size tilt.

    The standing rule is `feedback_ask_what_it_bought`: print the DATES and the
    HOLDINGS before shipping a signal, because statistics cannot tell you that
    a rule is a description of its own sample. `liquid` had the best t on the
    grid and was a FAANG list.
    """
    permnos = panel.permnos
    counts: dict[int, int] = {}
    prev: set[int] = set()
    turnovers = []
    size_pct, age_pct = [], []
    mktcap = panel.mktcap.astype(np.float64)
    # permno order is assignment order, so it is an UNCENSORED listing-age
    # proxy — unlike a first-observation row, which every panel clamps at its
    # own left edge.
    pn = permnos.astype(np.float64)

    for n, r in enumerate(rows):
        m = elig[n] & np.isfinite(sig[n])
        idx = np.flatnonzero(m)
        if idx.size == 0:
            continue
        chosen = idx[np.argsort(-sig[n][idx], kind="stable")[:top_k]]
        cur = set(int(permnos[c]) for c in chosen)
        for c in cur:
            counts[c] = counts.get(c, 0) + 1
        if prev:
            turnovers.append(1.0 - len(cur & prev) / max(len(cur), 1))
        prev = cur

        # BOTH percentiles are against the ELIGIBLE set on that date, never
        # against the panel. The book chooses from the top-`universe_n` by
        # dollar volume, and that set is far older and larger than the panel
        # as a whole — so a panel-relative percentile would report a book of
        # ancient mega-caps as "average age" and hide the exact confound this
        # census exists to expose.
        mc, univ_mc = mktcap[r][chosen], mktcap[r][idx]
        good = np.isfinite(mc)
        uf = univ_mc[np.isfinite(univ_mc)]
        if good.any() and uf.size > 5:
            size_pct.append(float(np.mean(
                [(uf < v).mean() for v in mc[good]])) * 100.0)
        ua = pn[idx]
        if ua.size > 5:
            age_pct.append(float(np.mean(
                [(ua < v).mean() for v in pn[chosen]])) * 100.0)

    top = sorted(counts.items(), key=lambda kv: -kv[1])[:n_report]
    n_dates = max(len(rows), 1)
    return {
        "n_formation_dates": int(len(rows)),
        "n_distinct_names_ever_held": len(counts),
        "top_names_by_selection_count": [
            {"permno": p, "dates_held": c,
             "pct_of_dates": round(100.0 * c / n_dates, 1)} for p, c in top],
        # A book of `top_k` names over `n_dates` dates that only ever holds
        # ~`top_k` names is a static list wearing a signal's name.
        "distinct_names_per_slot": round(len(counts) / max(top_k, 1), 2),
        "mean_turnover_pct": (round(100.0 * float(np.mean(turnovers)), 1)
                              if turnovers else None),
        # DESCRIPTIVE, not PIT — see the module docstring.
        "mean_size_percentile_of_holdings": (round(float(np.mean(size_pct)), 1)
                                             if size_pct else None),
        "mean_permno_percentile_of_holdings": (round(float(np.mean(age_pct)), 1)
                                               if age_pct else None),
        "permno_percentile_note":
            "permno is assigned in listing order, so a LOW percentile means "
            "OLD listings. Measured against the ELIGIBLE set on each date, so "
            "50 means 'typical age for a name this book could have bought' — "
            "NOT typical for the panel, which is much younger. This is the "
            "axis on which raw profit_roe was confounded.",
        "percentile_baseline": "eligible set on each formation date",
    }


def signal_report(panel, signal_name: str, *, policy=None, top_k: int = 20,
                  holding_days: int = 21, warmup: int | None = None,
                  n_quantiles: int = DEFAULT_QUANTILES, seed: int = 0,
                  phase_offset: int = 0) -> dict:
    """The whole cross-sectional picture for one signal, before any book.

    Order is deliberate and is the point of the module: IC, then the quantile
    curve, then what a top-k slice of it would have held. A signal that fails
    the first two does not get a terminal wealth quoted at all.
    """
    from . import signals as SIG
    from .policy import Policy
    from .replay import DEFAULT_WARMUP, eligible_at

    pol = policy or Policy(signal=signal_name, top_k=top_k,
                           holding_days=holding_days)
    w0 = DEFAULT_WARMUP if warmup is None else int(warmup)

    sig_full = SIG.matrix(panel, signal_name, seed=seed)
    rows = formation_rows(panel, holding_days, w0, phase_offset)
    if rows.size < 4:
        return {"signal": signal_name,
                "error": f"only {rows.size} non-overlapping formation dates at "
                         f"holding_days={holding_days}; a panel this short "
                         f"cannot support the diagnostic"}

    # Trailing dollar-volume mean, the liquidity rank `eligible_at` screens on.
    # THE WINDOW AND min_obs MUST MATCH `replay.run` EXACTLY — it computes
    # `_roll_mean(dolvol, SIG.MONTH, 5)`. Sharing `eligible_at` is worthless if
    # the two callers hand it different inputs: a different `min_obs` changes
    # which names have a finite `liq`, which changes eligibility, which is the
    # precise drift the shared definition exists to prevent.
    liq = SIG._roll_mean(panel.dolvol.astype(np.float64), SIG.MONTH, 5)

    elig = np.zeros((rows.size, panel.close.shape[1]), dtype=bool)
    for n, r in enumerate(rows):
        elig[n] = eligible_at(panel, int(r), pol, liq[r])

    sig = sig_full[rows]
    fwd = forward_returns(panel, rows, holding_days)

    ic = rank_ic(sig, fwd, elig)
    qp = quantile_profile(sig, fwd, elig, n_q=n_quantiles,
                          holding_days=holding_days)
    cen = selection_census(panel, sig, rows, elig, top_k)

    return {
        "signal": signal_name,
        "window": [str(panel.dates[rows[0]]), str(panel.dates[rows[-1]])],
        "holding_days": int(holding_days),
        "top_k": int(top_k),
        "universe_n": int(pol.universe_n),
        "is_null": signal_name in SIG.NULL_SIGNALS,
        "rank_ic": ic,
        "quantiles": qp,
        "census": cen,
        "verdict": _verdict(ic, qp, cen),
    }


def _verdict(ic: dict, qp: dict, cen: dict) -> dict:
    """A signal is worth a portfolio only if the cross section says so first.

    Three conditions, each of which a previously-shipped farm result failed:

      * `ic_t` — momentum's own terminal wealth was never accompanied by one;
      * monotone quantiles — `liquid` would fail this and did not have to;
      * more names than slots — a static list is not a signal, and this is the
        cheapest possible detector for one.

    DELIBERATELY NOT A GATE. Under the three-licence rule this verdict governs
    what may be CLAIMED and what deserves the next hour, not what may be
    tested in paper. A `PRODUCT_EXPERIMENT` may launch on a plausible mechanism
    that fails a significance bar; it should not launch on a signal whose
    quantile curve is flat, because that is not a weak edge, it is no edge.
    """
    reasons = []
    ic_t = ic.get("ic_t")
    if ic_t is None:
        reasons.append("no usable IC")
    elif abs(ic_t) < 2.0:
        reasons.append(f"IC t={ic_t} below 2")
    mono = qp.get("monotonicity_spearman")
    reversed_ = mono is not None and np.isfinite(mono) and mono <= -0.6
    if reversed_:
        # A strongly NEGATIVE monotonicity is not "no signal" — it is a signal
        # pointing the other way, and reporting it as "not monotone" buries the
        # only actionable part. `value_bm` reads -0.90 over 32 years: extreme
        # top-k value in a mega-liquid universe selects distress, so the
        # NEGATED signal is the one with a positive cross section here.
        reasons.append(
            f"monotone in the REVERSED direction (spearman={mono}) — this is "
            f"a signal pointing the other way, not an absent one; diagnose "
            f"the negated signal")
    elif not qp.get("is_monotone"):
        reasons.append(f"quantiles not monotone (spearman={mono})")
    dps = cen.get("distinct_names_per_slot")
    if dps is not None and dps < 2.0:
        reasons.append(f"only {dps} distinct names per slot — a static list")
    return {
        "cross_section_supports_a_book": not reasons,
        "reversed_signal_worth_testing": bool(reversed_),
        "failed": reasons,
        "note": "advisory, not a gate: this governs what may be CLAIMED and "
                "what deserves the next hour of work, never what may be "
                "tested in paper (three-licence rule)",
    }
