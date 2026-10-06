"""Snowball FOLLOW-THROUGH as a free shadow series (CHUNK C18, 2026-10-07). Offline, $0.

Question (TRIAL-ANALYST-SNOWBALL-1 primary 1, UNSIGNED draft): after a raise
that ends a >= 90-day spell with no raise by any firm (t0), do >= 2 OTHER
distinct firms raise within 63 XNYS sessions? One row per t0 in
`analyst/snowball_shadow.jsonl`, with `probability` = an EXPANDING-WINDOW base
rate, graded by `grade_due` (the forecast ledger's `belief_state.resolve_one`
reads only prices, so it cannot grade this: spec §4.1). Nothing trades.

CONSTRUCTION (frozen in backend/config.py SNOWBALL_*, before any row was read)
----------------------------------------------------------------------------
* raises = dated `target_action` raises, first seen strictly before the run,
  one per (ticker, day, firm).
* t0 flag = `crsp_pit_bridges.first_movers(raises, gap_days=90)` on the live
  analyst file (ticker stands in for permno), PLUS the trial's coverage-start
  exclusion read literally: the ticker's first raise is at least
  SNOWBALL_HISTORY_DAYS before the 90-day quiet window (day - 180 days).
  NOTE: the draft's own count (24,323, a 10.5% cut) reproduces the looser
  reading (history >= 90 days before the DAY); that discrepancy is printed on
  the build note for the signer, not resolved here by choosing the friendlier one.
* One event per (ticker, t0 day). `t0_brokers` = every firm raising that day
  (no within-day order is known), so a same-day co-raiser is never a follower.
* outcome = 1 if >= 2 distinct firms NOT in t0_brokers raise with an XNYS
  session in (s0, s0 + 63], s0 = the first session on/after the t0 day.
* probability = (k + a) / (n + 2a), a = SNOWBALL_PRIOR_PSEUDO / 2, over prior
  events whose window CLOSED strictly before this t0 day AND within the trailing
  SNOWBALL_BASE_WINDOW_MONTHS (24) -- never the full-sample 36% (the PIT trap the
  spec names in §4.3). Review C18 F9: the all-history mean (ledger schema 1.0.0,
  archived beside this one) lagged the coverage-driven drift by ~10pp.
* evidence = FORWARD only when the row is written within
  SNOWBALL_FORWARD_MAX_LAG_DAYS of its t0 day; every other row is REPLAY
  (history, graded at once, never forward evidence).

The return leg is NOT here (unregistered, unpowered). `cross_sectional_rho`
is the one measurement the draft owed before it can be re-linted.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services import analyst_reputation as AR
from backend.services.crsp_pit_bridges import first_movers

LEDGER = AR.ANALYST_DIR / "snowball_shadow.jsonl"
RHO_DIR = AR.ANALYST_DIR
GAP = _config.SNOWBALL_GAP_DAYS
HIST = _config.SNOWBALL_HISTORY_DAYS
H = _config.SNOWBALL_HORIZON_SESSIONS
THRESH = _config.SNOWBALL_THRESHOLD
PSEUDO = _config.SNOWBALL_PRIOR_PSEUDO
BASE_MONTHS = _config.SNOWBALL_BASE_WINDOW_MONTHS
FWD_LAG = _config.SNOWBALL_FORWARD_MAX_LAG_DAYS
OBSERVABLE = "analyst_follow_through_ge2"
SPECIALIST = "analyst_snowball_followthrough"
SCHEMA_VERSION = "1.1.0"   # 1.1.0: trailing 24-month base rate (review F9)
BASE_RATE_RULE = (f"trailing {BASE_MONTHS} months: (k + {PSEUDO / 2:g}) / (n + {PSEUDO:g}) over t0 events whose "
                  f"{H}-session window closed strictly before the row's t0 day and on/after t0 - {BASE_MONTHS} months")


class SnowballRefused(RuntimeError):
    """The shadow series will not write or grade a row it cannot date."""


# ───────────────────────────── calendar ─────────────────────────────

def xnys_sessions(start: str = "2006-10-09", end: Optional[str] = None) -> pd.DatetimeIndex:
    """XNYS sessions from exchange_calendars (covers ~1 year ahead). Refuses without it:
    a weekday calendar would count Good Friday and Thanksgiving as sessions."""
    try:
        import exchange_calendars as xc  # noqa: PLC0415
    except ImportError as exc:
        raise SnowballRefused("exchange_calendars not installed: no XNYS session calendar") from exc
    cal = xc.get_calendar("XNYS")
    end = end or str(cal.last_session.date())
    return pd.DatetimeIndex(cal.sessions_in_range(max(pd.Timestamp(start), cal.first_session),
                                                  min(pd.Timestamp(end), cal.last_session))).tz_localize(None)


# ───────────────────────────── events ─────────────────────────────

def raises_known(rv: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    from backend.services.revision_flow import _normalise_action, _RAISE  # noqa: PLC0415
    k = AR.known_before(rv, asof)
    r = k[_normalise_action(k["target_action"]) == _RAISE].copy()
    r["day"] = r["event_date"].dt.normalize()
    return r.drop_duplicates(["ticker", "day", "firm"])[["ticker", "day", "firm"]].reset_index(drop=True)


def t0_events(raises: pd.DataFrame, sessions: pd.DatetimeIndex, *, gap_days: int = GAP,
              hist_days: int = HIST, horizon: int = H) -> pd.DataFrame:
    """One row per (ticker, t0 day): t0_brokers, s0 index, resolves_after (session s0 + horizon)."""
    cols = ["ticker", "day", "t0_brokers", "s0", "resolves_after"]
    if raises.empty:
        return pd.DataFrame(columns=cols)
    r = raises.reset_index(drop=True)
    fm = first_movers(r.rename(columns={"ticker": "permno"})[["permno", "day"]], gap_days=gap_days)
    first = r.groupby("ticker")["day"].transform("min")
    cov = (first <= r["day"] - pd.Timedelta(days=gap_days + hist_days)).to_numpy()
    t = r[fm & cov]
    ev = t.groupby(["ticker", "day"])["firm"].agg(lambda s: sorted(set(s))).reset_index(name="t0_brokers")
    sv = sessions.values.astype("datetime64[ns]")
    ev["s0"] = np.searchsorted(sv, ev["day"].values.astype("datetime64[ns]"), side="left")
    ok = ev["s0"] + horizon < len(sv)
    ev = ev[ok].copy()          # beyond the calendar: written on a later night
    ev["resolves_after"] = pd.to_datetime(sv[ev["s0"].to_numpy() + horizon])
    return ev.sort_values(["day", "ticker"]).reset_index(drop=True)[cols]


def follow_through(ev: pd.DataFrame, raises: pd.DataFrame, sessions: pd.DatetimeIndex, *,
                   horizon: int = H) -> pd.Series:
    """Count of distinct firms (not t0 brokers) raising in sessions (s0, s0 + horizon]."""
    sv = sessions.values.astype("datetime64[ns]")
    rr = raises.assign(s=np.searchsorted(sv, raises["day"].values.astype("datetime64[ns]"), side="left"))
    by_t = {t: g for t, g in rr.groupby("ticker")}
    out = []
    for tkr, s0, brokers in zip(ev["ticker"], ev["s0"], ev["t0_brokers"]):
        g = by_t.get(tkr)
        if g is None:
            out.append(0)
            continue
        m = (g["s"] > s0) & (g["s"] <= s0 + horizon) & ~g["firm"].isin(brokers)
        out.append(int(g.loc[m, "firm"].nunique()))
    return pd.Series(out, index=ev.index, dtype=int)


def expanding_base_rate(day: pd.Series, resolves_after: pd.Series, outcome: pd.Series, *,
                        pseudo: float = PSEUDO, window_months: Optional[int] = BASE_MONTHS
                        ) -> tuple[np.ndarray, np.ndarray]:
    """(probability, n_prior) per event from events whose window closed STRICTLY before its
    day and (when `window_months` is set) on or after day - window_months.

    An event with an unknown outcome (NaN) never enters the base rate.
    """
    a = pseudo / 2.0
    known = outcome.notna().to_numpy()
    ra = resolves_after.to_numpy(dtype="datetime64[ns]")[known]
    oc = outcome.to_numpy(dtype=float)[known]
    order = np.argsort(ra, kind="mergesort")
    ra, oc = ra[order], oc[order]
    cum = np.concatenate([[0.0], np.cumsum(oc)])
    d = day.to_numpy(dtype="datetime64[ns]")
    hi = np.searchsorted(ra, d, side="left")                    # ra < day strictly
    if window_months:
        start = (pd.DatetimeIndex(d) - pd.DateOffset(months=window_months)).to_numpy(dtype="datetime64[ns]")
        lo = np.searchsorted(ra, start, side="left")            # ra >= day - window
    else:
        lo = np.zeros_like(hi)
    n = hi - lo
    k = cum[hi] - cum[lo]
    return (k + a) / (n + 2 * a), n


# ───────────────────────────── the ledger ─────────────────────────────

def _pid(ticker: str, day: pd.Timestamp) -> str:
    return "snow_" + hashlib.sha256(f"{ticker}|{day.date()}|{OBSERVABLE}|{H}".encode()).hexdigest()[:16]


def read_ledger(path: Path = LEDGER) -> list[dict]:
    if not Path(path).exists():
        return []
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_ledger(rows: list[dict], path: Path, n_before: int) -> None:
    if len(rows) < n_before:
        raise SnowballRefused(f"refusing to shrink the shadow ledger ({n_before} -> {len(rows)} rows)")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")
    if sum(1 for ln in tmp.read_text(encoding="utf-8").splitlines() if ln.strip()) != len(rows):
        raise SnowballRefused("shadow ledger temp file did not verify")
    tmp.replace(path)


def run(now: Optional[datetime] = None, *, rv: Optional[pd.DataFrame] = None,
        sessions: Optional[pd.DatetimeIndex] = None, path: Path = LEDGER,
        weights_tabs: Optional[dict] = None) -> dict:
    """Append rows for t0 events not yet in the ledger, then grade every due row."""
    now = now or datetime.now(timezone.utc)
    asof = pd.Timestamp(now.astimezone(timezone.utc).replace(tzinfo=None)).floor("min")
    rv = AR.load_revisions() if rv is None else rv
    sessions = xnys_sessions() if sessions is None else sessions
    raises = raises_known(rv, asof)
    ev = t0_events(raises, sessions)
    if ev.empty:
        raise SnowballRefused("no t0 event on the analyst file: nothing to forecast (refusing, not zero)")
    # outcomes as of now, used ONLY for the base rate of LATER events (window closed before their day)
    due = ev["resolves_after"] < asof.normalize()
    k = follow_through(ev, raises, sessions)
    oc = pd.Series(np.where(due, (k >= THRESH).astype(float), np.nan), index=ev.index)
    prob, n_prior = expanding_base_rate(ev["day"], ev["resolves_after"], oc)
    rows = read_ledger(path)
    old_schema = sorted({str(r.get("schema_version")) for r in rows} - {SCHEMA_VERSION})
    archived = None
    if old_schema:
        # a construction change starts a NEW ledger; the old one is renamed, never edited
        stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archived = path.with_name(f"{path.stem}_schema{'_'.join(old_schema)}_{stamp}{path.suffix}")
        if archived.exists():
            raise SnowballRefused(f"refusing to overwrite the archived ledger {archived.name}")
        path.replace(archived)
        rows = []
    n_before = len(rows)
    have = {r["prediction_id"] for r in rows}
    tabs = weights_tabs
    new = 0
    for i, e in ev.iterrows():
        pid = _pid(e["ticker"], e["day"])
        if pid in have:
            continue
        lag = (asof.normalize() - e["day"]).days
        w = None
        # only a FORWARD row may carry today's weights: on a REPLAY row they would be
        # weights resolved years after its t0 (reported-only, but still a look-ahead)
        if tabs is not None and lag <= FWD_LAG:
            sec = AR.sector_map([e["ticker"]]).get(e["ticker"], "UNKNOWN")
            w = round(AR.cell_weight(tabs, e["t0_brokers"][0], sec)["weight"], 4)
        rows.append({
            "prediction_id": pid, "ticker": e["ticker"], "specialist": SPECIALIST, "observable": OBSERVABLE,
            "horizon_days": H, "probability": round(float(prob[i]), 6), "threshold": THRESH,
            "made_at": str(e["day"].date()), "written_at": now.isoformat(timespec="seconds"),
            "resolves_after": str(e["resolves_after"].date()),
            "evidence": "FORWARD" if lag <= FWD_LAG else "REPLAY",
            "t0_brokers": list(e["t0_brokers"]),
            "t0_firm_reputation_weight": w,
            "base_rate_n_prior": int(n_prior[i]),   # rule: BASE_RATE_RULE (module constant)
            "resolved_at": None, "outcome": None, "brier": None, "resolution_detail": {},
            "schema_version": SCHEMA_VERSION,
        })
        new += 1
    graded = grade_due(rows, raises, sessions, today=asof.normalize(), now=now)
    _write_ledger(rows, path, n_before)
    return {"status": "ok", "path": str(path), "rows_total": len(rows), "rows_new": new,
            "rows_graded_now": graded, "n_t0_events": int(len(ev)),
            "forward_new": sum(1 for r in rows[n_before:] if r["evidence"] == "FORWARD"),
            "first_seen_basis": rv.attrs.get("first_seen_basis"), "asof": asof.isoformat(),
            "archived_previous_schema": archived.name if archived else None}


def grade_due(rows: list[dict], raises: pd.DataFrame, sessions: pd.DatetimeIndex, *,
              today: pd.Timestamp, now: datetime) -> int:
    """Parallel to belief_state.resolve_one: graded -> no-op; not yet due -> no-op;
    else outcome / brier / resolved_at from the raises FIRST SEEN before now."""
    todo = [r for r in rows if r.get("outcome") is None and pd.Timestamp(r["resolves_after"]) < today]
    if not todo:
        return 0
    sv = sessions.values.astype("datetime64[ns]")
    ev = pd.DataFrame({"ticker": [r["ticker"] for r in todo],
                       "t0_brokers": [r["t0_brokers"] for r in todo],
                       "s0": np.searchsorted(sv, pd.to_datetime([r["made_at"] for r in todo]).values
                                             .astype("datetime64[ns]"), side="left")})
    k = follow_through(ev, raises, sessions)
    for r, kk in zip(todo, k):
        o = int(kk >= THRESH)
        r["outcome"] = o
        r["brier"] = round((float(r["probability"]) - o) ** 2, 6)
        r["resolved_at"] = now.isoformat(timespec="seconds")
        r["resolution_detail"] = {"n_other_firms_raised": int(kk)}
    return len(todo)


def _brier_block(g: pd.DataFrame) -> dict:
    if g.empty:
        return {"graded": 0, "brier": None, "brier_constant_rate_LOOKAHEAD": None}
    base = float(g["outcome"].mean())
    return {"graded": int(len(g)), "outcome_rate": round(base, 4),
            "mean_probability": round(float(g["probability"].mean()), 4),
            "brier": round(float(g["brier"].mean()), 5),
            # a constant at THIS subset's own realised rate: uses the outcomes it is scored on
            "brier_constant_rate_LOOKAHEAD": round(float(((base - g["outcome"]) ** 2).mean()), 5)}


def summary(rows: list[dict]) -> dict:
    """REPLAY and FORWARD never blend (review F9): each gets its own Brier and its own
    constant-rate baseline."""
    df = pd.DataFrame(rows)
    if df.empty:
        return {"rows": 0}
    df["year"] = df["made_at"].str[:4]
    out: dict[str, Any] = {"rows": int(len(df)), "base_rate_rule": BASE_RATE_RULE,
                           "by_evidence": df.groupby("evidence").size().to_dict()}
    for ev in ("REPLAY", "FORWARD"):
        sub = df[df["evidence"] == ev]
        g = sub[sub["outcome"].notna()]
        out[ev.lower()] = {"rows": int(len(sub)), "by_year": sub.groupby("year").size().to_dict(),
                           "outcome_rate_by_year": g.groupby("year")["outcome"].mean().round(4).to_dict(),
                           "mean_probability_by_year": sub.groupby("year")["probability"].mean().round(4).to_dict(),
                           **_brier_block(g)}
    return out


# ───────────────────────────── cross_sectional_rho ─────────────────────────────

def cross_sectional_rho(rv: Optional[pd.DataFrame] = None, closes: Optional[pd.DataFrame] = None, *,
                        horizon: int = 21, seed: int = _config.SNOWBALL_RHO_SEED,
                        n_boot: int = _config.SNOWBALL_RHO_BOOT, asof: Optional[pd.Timestamp] = None) -> dict:
    """Intra-month correlation of 21-session SPY-excess returns of raise events.

    Policy-free surrogate (the draft's words): EVERY dated raise, one per (ticker,
    month), not the t0 selection. Entry = close of the first session strictly
    after the event day. rho = one-way random-effects ICC with calendar month as
    the group (ANOVA estimator, n0-adjusted); CI = month-block bootstrap. Then
    the design effect m / (1 + (m - 1) rho) re-prices the linter's R13b cap.
    """
    rv = AR.load_revisions() if rv is None else rv
    closes = AR.load_closes() if closes is None else closes
    asof = pd.Timestamp(asof) if asof is not None else pd.Timestamp.now(tz="UTC").tz_localize(None)
    rs = raises_known(rv, asof)
    rs = rs[rs["ticker"].isin(closes.columns)]
    dates = closes.index.values.astype("datetime64[ns]")
    i0 = np.searchsorted(dates, rs["day"].values.astype("datetime64[ns]"), side="right")
    i1 = i0 + horizon
    ok = (i0 >= 1) & (i1 < len(dates))
    rs, i0, i1 = rs[ok], i0[ok], i1[ok]
    ci = closes.columns.get_indexer(rs["ticker"])
    px = closes.to_numpy(dtype=float)
    spy = closes["SPY"].to_numpy(dtype=float)
    exc = (px[i1, ci] / px[i0, ci] - 1.0) - (spy[i1] / spy[i0] - 1.0)
    d = pd.DataFrame({"ticker": rs["ticker"].to_numpy(), "month": rs["day"].dt.strftime("%Y-%m").to_numpy(),
                      "exc": exc})
    d = d[np.isfinite(d["exc"])]
    # winsorise at 1/99 so one +900% microcap does not set the between-month variance
    lo, hi = d["exc"].quantile([0.01, 0.99])
    d["exc"] = d["exc"].clip(lo, hi)
    d = d.drop_duplicates(["ticker", "month"])
    if d["month"].nunique() < 3:
        raise SnowballRefused("fewer than 3 months of graded raise events: no ICC")

    def icc(frame: pd.DataFrame) -> float:
        g = frame.groupby("month")["exc"]
        m_i = g.size().to_numpy(dtype=float)
        k, n = len(m_i), m_i.sum()
        grand = frame["exc"].mean()
        ssb = float((m_i * (g.mean().to_numpy() - grand) ** 2).sum())
        ssw = float(((frame["exc"] - g.transform("mean")) ** 2).sum())
        msb, msw = ssb / (k - 1), ssw / (n - k)
        n0 = (n - (m_i ** 2).sum() / n) / (k - 1)
        return float((msb - msw) / (msb + (n0 - 1) * msw))

    rho = icc(d)
    rng = np.random.default_rng(seed)
    months = d["month"].unique()
    groups = {m: g for m, g in d.groupby("month")}
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(months, size=len(months), replace=True)
        f = pd.concat([groups[m].assign(month=f"{m}#{j}") for j, m in enumerate(pick)], ignore_index=True)
        boots.append(icc(f))
    lo_ci, hi_ci = np.percentile(boots, [2.5, 97.5])
    per_month = d.groupby("month").size()
    m_bar = float(per_month.mean())
    sd = float(d["exc"].std(ddof=1))
    z = 1.959964 + 0.841621                                       # two-sided 5%, 80% power
    effect = 0.004
    n_req = (z * sd / effect) ** 2
    ev_all = pd.to_datetime(rv["event_date"])
    yf_years = float((ev_all.max() - ev_all.min()).days / 365.25)
    # the draft's R13 inputs: 1,500 events/yr over 26 corpus-years, n_required 7,064, cap 12/yr
    ev_per_month = 1500 / 12.0

    def n_avail(r: float, years: float = 26.0) -> float:
        r = max(r, 0.0)
        return years * 12 * ev_per_month / (1 + (ev_per_month - 1) * r)
    avail_yf = n_avail(rho, yf_years)
    avail_yf_hi_rho = n_avail(float(hi_ci), yf_years)
    relintable = avail_yf_hi_rho >= n_req
    return {
        "schema": "snowball_rho/1", "asof": asof.isoformat(timespec="minutes"),
        "surrogate": "every dated target RAISE on the yfinance file, one per (ticker, month), entry at the close "
                     "of the first session strictly after the event day, 21-session return minus SPY, "
                     "winsorised 1/99; grouped by event month",
        "bars": "prices_2025_26/bars.parquet (2025-01 onward): ~20 months, so the CI is wide",
        "n_events": int(len(d)), "n_months": int(len(per_month)), "events_per_month_mean": round(m_bar, 1),
        "rho": round(rho, 5), "rho_ci95_month_bootstrap": [round(float(lo_ci), 5), round(float(hi_ci), 5)],
        "n_boot": n_boot, "seed": seed,
        "lint_inputs_reused": {"event_frequency_per_year": 1500, "corpus_years": 26, "n_required": 7064,
                               "n_available_at_cap": 312},
        "n_available_at_rho_26y_IBES_ASSUMED": round(n_avail(rho), 1),
        "n_available_at_rho_ci_26y_IBES_ASSUMED": [round(n_avail(float(hi_ci)), 1), round(n_avail(float(lo_ci)), 1)],
        "measured_sd_21s_excess": round(sd, 5),
        "n_required_at_measured_sd": round(n_req, 0),
        "yfinance_corpus_years": round(yf_years, 2),
        "n_available_on_yfinance_corpus": round(avail_yf, 1),
        "n_available_on_yfinance_corpus_at_rho_ci_hi": round(avail_yf_hi_rho, 1),
        "power_line": (f"On this corpus ({yf_years:.1f} y of yfinance raises) only ~{avail_yf:,.0f} usable observations "
                       f"(~{avail_yf_hi_rho:,.0f} at the upper rho) vs ~{n_req:,.0f} required -> "
                       + ("RE-LINTABLE" if relintable else "NOT RE-LINTABLE ON THIS CORPUS")
                       + ". 26 years (and the 11k figure) hold only if the IBES t0 count supports >= 1,500/yr, which "
                         "the draft says is owed before signing. The declared 0.4pp per 21 sessions is about the size "
                         "of the ~35 bps 21-day toll (section 59): economically marginal even if resolvable. The "
                         f"surrogate's own mean is {d['exc'].mean() * 100:+.2f}% per 21 sessions vs SPY."),
        "verdict": "RELINTABLE_ON_THIS_CORPUS" if relintable else "NOT_RELINTABLE_ON_THIS_CORPUS",
        "caveats": ["21-session windows that start late in one month overlap the next month's: the month "
                    "grouping understates dependence across adjacent months",
                    "the surrogate is all raises, not t0 events; t0 events may cluster differently",
                    "rho is measured on 2025-26 only; the linter's 26 corpus-years are assumed to share it",
                    "rho is biased LOW: month ICC on overlapping 21-session windows, winsorised 1/99, ignoring "
                    "same-sector clustering within a month"],
        "supersedes": "snowball_rho_20261006T214926Z.json (its 11,241 used 26 IBES years; this corpus has fewer)",
    }


def write_rho_receipt(blob: dict, base: Optional[Path] = None) -> Path:
    d = base or RHO_DIR
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = d / f"snowball_rho_{stamp}.json"
    if p.exists():
        raise SnowballRefused(f"refusing to overwrite {p.name}")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(p)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="snowball_shadow")
    ap.add_argument("job", choices=("run", "rho", "summary"))
    a = ap.parse_args(argv)
    if a.job == "run":
        try:
            blob, _, _ = AR.monthly_receipt(pd.Timestamp.now(tz="UTC").tz_localize(None))
            tabs = AR.tables_from_receipt(blob)
        except Exception:                                           # noqa: BLE001
            tabs = None      # the reputation weight is reported, never deciding
        out = run(weights_tabs=tabs)
        out["summary"] = summary(read_ledger())
    elif a.job == "rho":
        out = cross_sectional_rho()
        out["path"] = str(write_rho_receipt(out))
    else:
        out = summary(read_ledger())
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
