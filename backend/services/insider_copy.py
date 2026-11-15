"""
CH-47 — the insider copy book, tested as the owner states it.
=============================================================

The owner (2026-11-14): *"some of the insiders made 300% ... copying their
portfolio after the SEC filings you could have made at least double the S&P"*.

Picking the insider who made 300% AFTER the fact is the survivor. The testable
form, and the only one this module computes:

  at each filing date, rank the filing insider by the record KNOWN THEN —
  open-market purchases only (Form 4 code P) whose outcome window had CLOSED
  strictly before that filing date — copy from the filing's public bound,
  hold H sessions, and compare against the market, against insiders with poor
  prior records, against every purchase unranked, and against random
  same-date, same-size-bucket names. Costs on, never zero.

Licence ``PRODUCT_EXPERIMENT`` (historical backtest). ``TRIAL-INSIDER-IC`` and
``TRIAL-CMP-INSIDER-IC`` accrue forward; nothing here reads or writes them.

THE TWO RULES THAT MAKE IT HONEST, ENFORCED HERE RATHER THAN BY INTENTION
-------------------------------------------------------------------------
1. **No peeking.** A 126-session outcome is unknown until 126 sessions later.
   ``prior_record`` counts a prior trade only when its exit session date is
   strictly before the ranking trade's filing date, and ``audit_prior_record``
   recomputes a deterministic sample with an independent slow loop and REFUSES
   (``InsiderCopyRefused``) if any score used an unclosed window.
2. **No entry before the public bound.** The SEC bulk files carry the filing
   DATE and no acceptance time, so the public bound is FILING_DATE 22:00 ET.
   ``entry_session_index`` returns the first session strictly AFTER the filing
   date; ``assert_entry_after_public`` refuses any entry on or before it.

Every function below is pure (arrays and DataFrames in, arrays and dicts out)
so the fast suite can test it on synthetic data; the CRSP / Form 4 loaders
live in ``scripts/insider_copy_backtest.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


class InsiderCopyRefused(RuntimeError):
    """A copy-book computation that would be dishonest refuses instead.

    Raised on: a missing or zero cost schedule, an entry on or before the
    filing date, a prior record that used an outcome window not yet closed,
    or an empty input where a result was asked for.
    """


# ─────────────────────────── costs ───────────────────────────────────────


def require_costs(bands: Sequence[tuple[float, float]] | None) -> tuple[tuple[float, float], ...]:
    """Validate a cost schedule ``((min_dollar_vol, round_trip_bps), ...)``.

    Refuses an empty schedule and any band whose cost is not strictly
    positive: a zero-cost copy book is a diagnostic, never a result.
    """
    if not bands:
        raise InsiderCopyRefused("no cost schedule: costs are never omitted")
    out = tuple(sorted(((float(a), float(b)) for a, b in bands), key=lambda x: -x[0]))
    for thr, bps in out:
        if not np.isfinite(bps) or bps <= 0:
            raise InsiderCopyRefused(f"cost band >= {thr:,.0f} has {bps} bps: zero cost refused")
    if out[-1][0] > 0:
        raise InsiderCopyRefused("cost schedule has no floor band (lowest threshold must be 0)")
    return out


def round_trip_cost(median_dollar_vol: np.ndarray,
                    bands: Sequence[tuple[float, float]] | None) -> np.ndarray:
    """Round-trip cost as a FRACTION for each trade; unknown volume pays the floor band."""
    sched = require_costs(bands)
    dv = np.asarray(median_dollar_vol, dtype=float)
    out = np.full(dv.shape, sched[-1][1], dtype=float)
    assigned = np.zeros(dv.shape, dtype=bool)
    for thr, bps in sched:
        m = np.isfinite(dv) & (dv >= thr) & ~assigned
        out[m] = bps
        assigned |= m
    if not np.all(out > 0):
        raise InsiderCopyRefused("a trade was assigned a non-positive cost")
    return out / 1e4


# ─────────────────────────── entry timing ────────────────────────────────


def entry_session_index(filing_dates: np.ndarray, sessions: np.ndarray) -> np.ndarray:
    """Index of the first session STRICTLY after each filing date; -1 if none.

    ``filing_dates`` and ``sessions`` are datetime64[D]-coercible. A filing on
    a Friday enters Monday; a filing on a holiday enters the next session; a
    filing on a session day never enters that day (the public bound is the
    filing day's 22:00 ET, after the close).
    """
    f = np.asarray(filing_dates, dtype="datetime64[D]")
    s = np.asarray(sessions, dtype="datetime64[D]")
    if s.size and np.any(np.diff(s.astype("int64")) <= 0):
        raise InsiderCopyRefused("session calendar is not strictly increasing")
    idx = np.searchsorted(s, f, side="right")
    idx = np.where(idx >= len(s), -1, idx)
    return idx.astype(np.int64)


def assert_entry_after_public(filing_dates: np.ndarray, sessions: np.ndarray,
                              entry_idx: np.ndarray) -> int:
    """Refuse if any entry session is on or before its filing date. Returns n checked."""
    f = np.asarray(filing_dates, dtype="datetime64[D]")
    s = np.asarray(sessions, dtype="datetime64[D]")
    e = np.asarray(entry_idx, dtype=np.int64)
    ok = e >= 0
    bad = ok & (s[np.where(ok, e, 0)] <= f)
    if bad.any():
        k = int(np.flatnonzero(bad)[0])
        raise InsiderCopyRefused(
            f"entry precedes the public bound: filing {f[k]} entered {s[e[k]]} "
            f"({int(bad.sum())} rows)")
    return int(ok.sum())


# ─────────────────────────── trades ──────────────────────────────────────


_CLASS_RANK = {"opportunistic": 2, "routine": 1, "unclassifiable": 0}


def aggregate_trades(buys: pd.DataFrame, cluster_min: int = 3) -> pd.DataFrame:
    """One copy trade per (insider_cik, permno, filing_date).

    Input columns: insider_cik, permno, filing_date, cmp_class, cluster_buyers,
    is_officer, is_director, is_tenpercent, dollar_value. The CMP label is the
    strongest one on the filing (opportunistic > routine > unclassifiable);
    ``cluster`` marks a filing on which >= ``cluster_min`` distinct insiders of
    the issuer had filed buys (the I1 table's own count).
    """
    need = {"insider_cik", "permno", "filing_date", "cmp_class", "cluster_buyers",
            "is_officer", "is_director", "is_tenpercent", "dollar_value"}
    miss = need - set(buys.columns)
    if miss:
        raise InsiderCopyRefused(f"buys missing columns {sorted(miss)}")
    if buys.empty:
        raise InsiderCopyRefused("no open-market purchases to aggregate")
    b = buys.copy()
    b["filing_date"] = pd.to_datetime(b["filing_date"]).dt.normalize()
    b["_cr"] = b["cmp_class"].map(_CLASS_RANK).fillna(0).astype(int)
    g = b.groupby(["insider_cik", "permno", "filing_date"], sort=True)
    out = g.agg(cr=("_cr", "max"), cluster_buyers=("cluster_buyers", "max"),
                is_officer=("is_officer", "max"), is_director=("is_director", "max"),
                is_tenpercent=("is_tenpercent", "max"), dollar_value=("dollar_value", "sum"),
                n_rows=("_cr", "size")).reset_index()
    inv = {v: k for k, v in _CLASS_RANK.items()}
    out["cmp_class"] = out.pop("cr").map(inv)
    out["cluster"] = out["cluster_buyers"].fillna(0) >= cluster_min
    return out


# ─────────────────────────── returns ─────────────────────────────────────


def cumulative_log(R: np.ndarray) -> np.ndarray:
    """``C`` with ``C[0] = 0`` and ``C[t+1] = sum(log1p(R[0..t]))``; NaN counts as 0.

    The sum over sessions a..b inclusive is ``C[b+1] - C[a]``.
    """
    L = np.log1p(np.nan_to_num(np.asarray(R, dtype=float), nan=0.0))
    C = np.zeros((L.shape[0] + 1,) + L.shape[1:], dtype=float)
    np.cumsum(L, axis=0, out=C[1:])
    return C


def window_returns(entry_idx: np.ndarray, col: np.ndarray, H: int, C: np.ndarray,
                   G: np.ndarray | None, mode: str) -> dict[str, np.ndarray]:
    """Raw return of each trade held ``H`` sessions.

    ``next_open``: buy the OPEN of session i, sell the close of i+H-1;
    ``G[i, col] = log(close_i / open_i)``; a missing open enters at the close
    of session i instead (later, never earlier) and is flagged.
    ``next_close``: buy the close of session i, sell the close of i+H.
    ``C`` is ``cumulative_log`` of the delisting-folded daily return matrix.
    """
    T = C.shape[0] - 1
    i = np.asarray(entry_idx, dtype=np.int64)
    c = np.asarray(col, dtype=np.int64)
    if mode == "next_open":
        j = i + H - 1
        valid = (i >= 0) & (j < T)
        ii, jj = np.where(valid, i, 0), np.where(valid, j, 0)
        g = G[ii, c] if G is not None else np.full(len(i), np.nan)
        open_missing = ~np.isfinite(g)
        g = np.where(open_missing, 0.0, g)
        lr = g + C[jj + 1, c] - C[ii + 1, c]
    elif mode == "next_close":
        j = i + H
        valid = (i >= 0) & (j < T)
        ii, jj = np.where(valid, i, 0), np.where(valid, j, 0)
        open_missing = np.zeros(len(i), dtype=bool)
        lr = C[jj + 1, c] - C[ii + 1, c]
    else:
        raise InsiderCopyRefused(f"unknown entry mode {mode!r}")
    r = np.where(valid, np.expm1(lr), np.nan)
    return {"r": r, "exit_idx": np.where(valid, j, -1), "valid": valid,
            "open_missing": open_missing & valid}


def market_returns(entry_idx: np.ndarray, H: int, M: np.ndarray, mode: str) -> np.ndarray:
    """Market return over the same sessions (close-to-close; ``M`` from ``cumulative_log``).

    ``next_open`` uses sessions i..i+H-1 including session i's full day (the
    index has no open print), ``next_close`` uses i+1..i+H.
    """
    T = M.shape[0] - 1
    i = np.asarray(entry_idx, dtype=np.int64)
    if mode == "next_open":
        a, b = i, i + H - 1
    elif mode == "next_close":
        a, b = i + 1, i + H
    else:
        raise InsiderCopyRefused(f"unknown entry mode {mode!r}")
    valid = (i >= 0) & (b < T)
    aa, bb = np.where(valid, a, 0), np.where(valid, b, 0)
    return np.where(valid, np.expm1(M[bb + 1] - M[aa]), np.nan)


def sample_controls(entry_idx: np.ndarray, col: np.ndarray, bucket_prev: np.ndarray,
                    alive: np.ndarray, k: int, seed: int) -> np.ndarray:
    """``k`` random names per trade from the trade's size bucket on the session
    before entry, alive (priced) on the entry session, excluding the issuer.

    ``bucket_prev[t, n]`` is the bucket of name n at session t (-1 = none);
    the bucket used for a trade entering at i is row i-1 (known at filing).
    Returns an ``(n_trades, k)`` array of column indices, -1 where the bucket
    had fewer than ``k`` other names. Deterministic in ``seed``.
    """
    if k <= 0:
        raise InsiderCopyRefused("a random control needs k >= 1")
    rng = np.random.default_rng(seed)
    i = np.asarray(entry_idx, dtype=np.int64)
    c = np.asarray(col, dtype=np.int64)
    out = np.full((len(i), k), -1, dtype=np.int64)
    order = np.argsort(i, kind="stable")
    i_sorted = i[order]
    starts = np.flatnonzero(np.r_[True, i_sorted[1:] != i_sorted[:-1]])
    ends = np.r_[starts[1:], len(i_sorted)]
    for s0, s1 in zip(starts, ends):
        t = int(i_sorted[s0])
        if t <= 0:
            continue
        rows = order[s0:s1]
        bprev = bucket_prev[t - 1]
        al = alive[t]
        for r in rows:
            b = bprev[c[r]]
            if b < 0:
                continue
            pool = np.flatnonzero((bprev == b) & al)
            pool = pool[pool != c[r]]
            if len(pool) < k:
                continue
            out[r] = rng.choice(pool, size=k, replace=False)
    return out


# ─────────────────────────── prior record (no peeking) ───────────────────


def _day_numbers(d: np.ndarray) -> np.ndarray:
    """Day numbers since 1970 as int64; NaT / negative -> -1 (no outcome)."""
    a = np.asarray(d)
    if a.dtype.kind == "M":
        a = a.astype("datetime64[D]")
        out = a.astype(np.int64)
        return np.where(np.isnat(a), -1, out)
    out = a.astype(np.int64)
    return np.where(out < 0, -1, out)


def prior_record(insider: np.ndarray, filing_day: np.ndarray, exit_day: np.ndarray,
                 excess: np.ndarray) -> pd.DataFrame:
    """For each trade, the filing insider's record over PRIOR trades whose
    outcome window closed strictly before this trade's filing date.

    ``filing_day`` / ``exit_day`` are integer day numbers (or datetime64[D]);
    a trade with no measurable outcome (NaN excess or no exit) never enters a
    record. Returns n_prior, sum_prior, hits_prior and max_used_exit (the
    latest exit day any counted trade had; -inf when none).
    """
    ins = pd.factorize(pd.Series(insider), sort=True)[0].astype(np.int64)
    fd = _day_numbers(filing_day)
    ex = _day_numbers(exit_day)
    x = np.asarray(excess, dtype=float)
    n = len(ins)
    usable = np.isfinite(x) & (ex >= 0)
    BIG = np.int64(1 << 22)              # day numbers stay well below 4.19M
    span_lo = int(min(fd.min(initial=0), ex[usable].min(initial=0)))
    off = np.int64(-span_lo + 1)
    key_used = ins[usable] * BIG + (ex[usable] + off)
    order = np.argsort(key_used, kind="stable")
    key_sorted = key_used[order]
    x_sorted = x[usable][order]
    ex_sorted = ex[usable][order]
    csum = np.r_[0.0, np.cumsum(x_sorted)]
    chit = np.r_[0, np.cumsum(x_sorted > 0)]
    # block start of each insider in the sorted used array
    q_hi = ins * BIG + (fd + off)                         # strictly before filing day
    q_lo = ins * BIG                                      # insider's block start
    hi = np.searchsorted(key_sorted, q_hi, side="left")
    lo = np.searchsorted(key_sorted, q_lo, side="left")
    cnt = hi - lo
    s = csum[hi] - csum[lo]
    h = chit[hi] - chit[lo]
    mx = np.where(cnt > 0, ex_sorted[np.maximum(hi - 1, 0)], np.iinfo(np.int64).min)
    return pd.DataFrame({"n_prior": cnt.astype(np.int64), "sum_prior": s,
                         "hits_prior": h.astype(np.int64), "max_used_exit": mx},
                        index=np.arange(n))


def prior_record_slow(insider: np.ndarray, filing_day: np.ndarray, exit_day: np.ndarray,
                      excess: np.ndarray, rows: np.ndarray) -> pd.DataFrame:
    """Independent reference implementation (a plain loop) for ``rows`` only."""
    fd = _day_numbers(filing_day)
    ex = _day_numbers(exit_day)
    x = np.asarray(excess, dtype=float)
    ins = np.asarray(insider)
    by: dict = {}
    for k in range(len(ins)):
        by.setdefault(ins[k], []).append(k)
    out = []
    for r in rows:
        n = s = h = 0
        for k in by[ins[r]]:
            if not np.isfinite(x[k]) or ex[k] < 0:
                continue
            if ex[k] < fd[r]:
                n += 1
                s += x[k]
                h += int(x[k] > 0)
        out.append((int(r), n, s, h))
    return pd.DataFrame(out, columns=["row", "n_prior", "sum_prior", "hits_prior"]).set_index("row")


def audit_prior_record(insider: np.ndarray, filing_day: np.ndarray, exit_day: np.ndarray,
                       excess: np.ndarray, record: pd.DataFrame, sample_n: int = 2000,
                       seed: int = 0) -> dict:
    """Refuse if any score could have seen an unclosed outcome.

    Two checks: (1) on EVERY row, ``max_used_exit`` is strictly before the
    filing day; (2) on a deterministic sample, an independent slow loop
    reproduces n_prior / sum_prior exactly. A planted leak — a record built
    from windows still open at the filing date — fails one or both.
    """
    fd = _day_numbers(filing_day)
    used = record["n_prior"].to_numpy() > 0
    mx = record["max_used_exit"].to_numpy()
    viol = used & (mx >= fd)
    if viol.any():
        raise InsiderCopyRefused(
            f"prior record used an outcome not closed at the filing date on {int(viol.sum())} rows")
    rng = np.random.default_rng(seed)
    n = len(record)
    rows = np.arange(n) if n <= sample_n else np.sort(rng.choice(n, size=sample_n, replace=False))
    ref = prior_record_slow(insider, filing_day, exit_day, excess, rows)
    got = record.loc[rows]
    bad_n = (got["n_prior"].to_numpy() != ref["n_prior"].to_numpy())
    bad_s = ~np.isclose(got["sum_prior"].to_numpy(), ref["sum_prior"].to_numpy(), rtol=1e-9, atol=1e-12)
    if bad_n.any() or bad_s.any():
        raise InsiderCopyRefused(
            f"prior record disagrees with the closed-window reference on "
            f"{int((bad_n | bad_s).sum())} of {len(rows)} audited rows")
    return {"rows_checked_exit_rule": int(n), "rows_checked_reference": int(len(rows)),
            "violations": 0}


def score(record: pd.DataFrame, mode: str, shrink_k: float, min_prior: int) -> np.ndarray:
    """Prior-record score; NaN when fewer than ``min_prior`` closed prior trades.

    ``shrunk_mean``: sum / (n + K). ``hit_rate``: (hits + 0.5K) / (n + K).
    """
    n = record["n_prior"].to_numpy().astype(float)
    if mode == "shrunk_mean":
        s = record["sum_prior"].to_numpy() / (n + shrink_k)
    elif mode == "hit_rate":
        s = (record["hits_prior"].to_numpy() + 0.5 * shrink_k) / (n + shrink_k)
    else:
        raise InsiderCopyRefused(f"unknown score mode {mode!r}")
    return np.where(n >= min_prior, s, np.nan)


def rank_labels(filing_dates: np.ndarray, scores: np.ndarray, top_pct: float, poor_pct: float,
                lookback_days: int, min_scores: int) -> np.ndarray:
    """'top' / 'poor' / 'mid' / 'no_cutoff' / 'ineligible' per trade.

    Cutoffs for a calendar month are the percentiles of the scores of eligible
    trades filed in ``[month_start - lookback_days, month_start)`` — every one
    of which was itself computed from windows closed before ITS filing date,
    so the cutoff is known at month start.
    """
    f = pd.to_datetime(pd.Series(filing_dates)).dt.normalize().to_numpy(dtype="datetime64[D]")
    s = np.asarray(scores, dtype=float)
    lab = np.where(np.isfinite(s), "no_cutoff", "ineligible").astype(object)
    elig = np.isfinite(s)
    fe, se = f[elig], s[elig]
    o = np.argsort(fe, kind="stable")
    fe, se = fe[o], se[o]
    months = np.unique(f.astype("datetime64[M]"))
    for m in months:
        m0 = m.astype("datetime64[D]")
        lo = np.searchsorted(fe, m0 - np.timedelta64(lookback_days, "D"), side="left")
        hi = np.searchsorted(fe, m0, side="left")
        if hi - lo < min_scores:
            continue
        w = se[lo:hi]
        top_cut, poor_cut = np.percentile(w, top_pct), np.percentile(w, poor_pct)
        inm = elig & (f.astype("datetime64[M]") == m)
        lab[inm & (s >= top_cut)] = "top"
        lab[inm & (s <= poor_cut)] = "poor"
        lab[inm & (s < top_cut) & (s > poor_cut)] = "mid"
    return lab


# ─────────────────────────── statistics ──────────────────────────────────


def _blocks(entry_idx: np.ndarray, H: int) -> np.ndarray:
    return np.asarray(entry_idx, dtype=np.int64) // int(H)


def block_means(values: np.ndarray, entry_idx: np.ndarray, H: int) -> pd.Series:
    """Equal-weight mean of the trades entering in each block of ``H`` sessions."""
    v = np.asarray(values, dtype=float)
    m = np.isfinite(v)
    return pd.Series(v[m]).groupby(_blocks(entry_idx, H)[m]).mean()


def _t(x: np.ndarray) -> tuple[float, float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return float(np.mean(x)) if len(x) else float("nan"), float("nan"), float("nan")
    se = float(np.std(x, ddof=1) / np.sqrt(len(x)))
    return float(np.mean(x)), se, float(np.mean(x) / se) if se > 0 else float("nan")


def series_stats(bm: pd.Series) -> dict:
    """t on H-blocks, and on alternate blocks (strictly non-overlapping windows:
    a window starting in block b ends before block b+2 begins). The MDE (80%
    power, 5% two-sided) is 2.8 x the non-overlap standard error."""
    mean_all, se_all, t_all = _t(bm.to_numpy())
    alt = [bm[bm.index % 2 == p].to_numpy() for p in (0, 1)]
    res = [_t(a) for a in alt]
    # report the parity with the larger standard error (the conservative one)
    k = int(np.nanargmax([r[1] if np.isfinite(r[1]) else -1 for r in res]))
    mean_alt, se_alt, t_alt = res[k]
    return {"n_blocks": int(len(bm)), "mean_block": mean_all, "se_block": se_all,
            "t_block": t_all, "n_blocks_nonoverlap": int(len(alt[k])),
            "mean_nonoverlap": mean_alt, "se_nonoverlap": se_alt,
            "t_nonoverlap": t_alt,
            "mde_nonoverlap": 2.8 * se_alt if np.isfinite(se_alt) else float("nan")}


def stats(values: np.ndarray, entry_idx: np.ndarray, H: int) -> dict:
    v = np.asarray(values, dtype=float)
    out = {"n_trades": int(np.isfinite(v).sum()),
           "mean_trade": float(np.nanmean(v)) if np.isfinite(v).any() else float("nan")}
    out.update(series_stats(block_means(v, entry_idx, H)))
    return out


def diff_stats(va: np.ndarray, ia: np.ndarray, vb: np.ndarray, ib: np.ndarray, H: int) -> dict:
    """Block-mean difference A - B on blocks where both sleeves traded."""
    a, b = block_means(va, ia, H), block_means(vb, ib, H)
    d = (a - b).dropna()
    out = series_stats(d)
    out["n_blocks_both"] = int(len(d))
    return out


def by_year(values: np.ndarray, entry_idx: np.ndarray, years: np.ndarray, H: int,
            dates: np.ndarray | None = None) -> list[dict]:
    v = np.asarray(values, dtype=float)
    y = np.asarray(years)
    out = []
    for yr in sorted(set(y[np.isfinite(v)].tolist())):
        m = (y == yr) & np.isfinite(v)
        bm = block_means(v[m], np.asarray(entry_idx)[m], H)
        row = {"year": int(yr), "n_trades": int(m.sum()), "mean_trade": float(v[m].mean()),
               "mean_block": float(bm.mean()), "n_blocks": int(len(bm))}
        if dates is not None:
            row["n_dates"] = int(len(np.unique(np.asarray(dates)[m])))
        out.append(row)
    return out


def leave_one_year_out(values: np.ndarray, entry_idx: np.ndarray, years: np.ndarray, H: int) -> dict:
    v = np.asarray(values, dtype=float)
    y = np.asarray(years)
    res = {}
    for yr in sorted(set(y[np.isfinite(v)].tolist())):
        m = (y != yr) & np.isfinite(v)
        res[int(yr)] = float(block_means(v[m], np.asarray(entry_idx)[m], H).mean()) if m.any() else float("nan")
    worst = min(res, key=lambda k: res[k]) if res else None
    return {"drop_year_mean_block": res, "worst_year_dropped": worst,
            "loo_worst_mean_block": res[worst] if worst is not None else float("nan")}


def concentration(values: np.ndarray, dates: np.ndarray, names: np.ndarray) -> dict:
    """Share of the summed result carried by the single best date / name (signed)."""
    v = pd.Series(np.asarray(values, dtype=float))
    m = v.notna().to_numpy()
    v = v[m]
    tot = float(v.sum())
    bd = v.groupby(np.asarray(dates)[m]).sum()
    bn = v.groupby(np.asarray(names)[m]).sum()
    def share(s: pd.Series) -> float:
        if tot == 0 or s.empty:
            return float("nan")
        pick = s.max() if tot > 0 else s.min()
        return float(pick / tot)
    top10 = (bd.sort_values(ascending=tot <= 0).head(10).sum() / tot) if tot else float("nan")
    return {"total_sum": tot, "top_date_share": share(bd), "top_name_share": share(bn),
            "top10_dates_share": float(top10),
            "top_date": str(bd.idxmax() if tot > 0 else bd.idxmin()) if len(bd) else None,
            "top_name": str(bn.idxmax() if tot > 0 else bn.idxmin()) if len(bn) else None}


def verdict(vs_market: dict, vs_poor: dict, vs_control: dict, loo_worst: float,
            share_years_positive: float, t_bar: float = 2.0) -> str:
    """House vocabulary, declared in the run's declaration file.

    OBSERVED: net excess vs market, vs poor-record insiders and vs the random
    control all > 0 with non-overlap t >= t_bar on the control and poor legs,
    the worst leave-one-year-out mean > 0 and a strict majority of years > 0.
    FAILED_VARIANT: net excess vs the random control < 0 with t <= -t_bar.
    Otherwise CANNOT_DISTINGUISH.
    """
    tc, tp = vs_control.get("t_nonoverlap", np.nan), vs_poor.get("t_nonoverlap", np.nan)
    if np.isfinite(tc) and tc <= -t_bar and vs_control.get("mean_nonoverlap", 0) < 0:
        return "FAILED_VARIANT"
    if (vs_market.get("mean_block", -1) > 0 and vs_poor.get("mean_block", -1) > 0
            and vs_control.get("mean_block", -1) > 0 and np.isfinite(tc) and tc >= t_bar
            and np.isfinite(tp) and tp >= t_bar and loo_worst > 0 and share_years_positive > 0.5):
        return "OBSERVED"
    return "CANNOT_DISTINGUISH"
