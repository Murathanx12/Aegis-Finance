"""The CONTEST DESK: every evening, a finished, checked order sheet for the owner.

    python -m scripts.contest_desk --date today            # write sheets/<date>.md and <date>.txt
    python -m scripts.contest_desk --dry-run 2026-09-14 2026-09-25   # the rehearsal on past dates

The rule (EARNINGS-MAGNITUDE ROTATION, from docs/reviews/REVIEW_2026-09-28_CONTEST_BOOK.md §4):
hold the five names reporting next, ranked by the average ABSOLUTE size of their last
eight earnings reactions, 20% each, sell after the report. It predicts the SIZE of the
move (rank correlation 0.33-0.44 in every year 2016-2026), NOT its direction. Every
version of it loses more often than it wins; it is a choice of variance for rank.

Nothing here places an order. The owner enters them on the Terminal (TMSG <GO>).
PRODUCT_EXPERIMENT; family of one; utility "contest rank, right tail". Whatever it
returns is never quoted as evidence of the project's skill.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc   # noqa: E402

SHEETS = cc.CONTEST / "sheets"
PREVIEW = cc.CONTEST / "preview"
DRY = cc.CONTEST / "dry_run"
STOP_FILE = cc.CONTEST / "STOP"
K_SLOTS = 5
WEIGHT = 0.20
MIN_PRIOR = 3
TRAIL_N = 8
MIN_PRICE_USD = 1.0
SHEET_HOUR_HKT = 14          # sheets are written ~14:30 HKT; the window runs to the next one
LICENCE = ("PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. "
           "Never evidence of skill.")


class SheetRefused(ValueError):
    """A sheet that would break a contest rule or use information dated after it."""


# ───────────────────────────── the panel ─────────────────────────────

@dataclass
class Panel:
    dates: pd.DatetimeIndex
    syms: pd.Index
    close: np.ndarray        # USD, NaN when the name did not trade
    open: np.ndarray
    dv63: np.ndarray         # rolling median $ volume (63 sessions of the name's own), USD
    sig63: np.ndarray        # rolling std of daily log returns
    market: np.ndarray       # per symbol
    col: dict = field(default_factory=dict)

    def idx(self, d: Any) -> int:
        """Index of the last panel date <= d."""
        return int(self.dates.searchsorted(pd.Timestamp(d), side="right")) - 1


def panel_from_long(b: pd.DataFrame, *, start: Optional[str] = None) -> Panel:
    b = b.copy()
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    if start:
        b = b[b.date >= pd.Timestamp(start)]
    b = b.drop_duplicates(["symbol", "date"])
    C = b.pivot(index="date", columns="symbol", values="close").sort_index().astype("float32")
    O = b.pivot(index="date", columns="symbol", values="open").reindex(C.index)[C.columns].astype("float32")
    V = b.pivot(index="date", columns="symbol", values="volume").reindex(C.index)[C.columns].astype("float32")
    DV = (C * V)
    # per-name rolling stats over the name's OWN sessions (NaN rows are other markets' days)
    dv = np.full(C.shape, np.nan, dtype="float32")
    sg = np.full(C.shape, np.nan, dtype="float32")
    Cv, DVv = C.to_numpy(), DV.to_numpy()
    for j in range(C.shape[1]):
        m = np.isfinite(Cv[:, j])
        if m.sum() < 20:
            continue
        s = pd.Series(DVv[m, j])
        dv[m, j] = s.rolling(63, min_periods=40).median().to_numpy()
        lr = np.log(pd.Series(Cv[m, j])).diff()
        sg[m, j] = lr.rolling(63, min_periods=40).std().to_numpy()
    # carry the last value across other markets' days (a stat is "as of" the name's last session)
    dv = pd.DataFrame(dv).ffill(limit=5).to_numpy(dtype="float32")
    sg = pd.DataFrame(sg).ffill(limit=5).to_numpy(dtype="float32")
    syms = C.columns
    mk = np.array([cc.market_of(s) for s in syms])
    return Panel(C.index, syms, Cv, O.to_numpy(), dv, sg, mk, {s: i for i, s in enumerate(syms)})


def load_panel(*, markets: Iterable[str] = tuple(cc.MARKETS), start: str = "2016-01-01",
               us_symbols: Optional[Iterable[str]] = None) -> Panel:
    b = cc.load_bars_usd([m for m in markets if m != "US"], include_us="US" in markets,
                         us_symbols=us_symbols)
    return panel_from_long(b, start=start)


# ───────────────────────────── events ─────────────────────────────

SOURCE_PRIORITY = {"sec_8k_2.02": 0, "CONFIRMED_EXCHANGE": 1, "CONFIRMED_COMPANY": 1,
                   "CONFIRMED_TERMINAL": 1, "yahoo_earnings_dates": 2, "VENDOR_ANNOUNCED": 3,
                   "nasdaq_calendar": 4, "VENDOR_ESTIMATE": 5, "ESTIMATED_PATTERN": 6}


def dedupe_stamps(raw: pd.DataFrame, *, days: int = 4) -> pd.DataFrame:
    """Stamps of one symbol within `days` of each other are ONE report. Keep the most
    primary source, and a timed stamp over a midnight (time unknown) one."""
    r = raw.copy()
    r["ts_utc"] = pd.to_datetime(r.ts_utc, utc=True)
    if "source" not in r.columns:
        r["source"] = ""
    r = r.sort_values(["symbol", "ts_utc"]).reset_index(drop=True)
    new_grp = (r.symbol != r.symbol.shift()) | ((r.ts_utc - r.ts_utc.shift()).dt.days > days)
    r["grp"] = new_grp.cumsum()
    loc_mid = r.ts_utc.dt.tz_convert("America/New_York")
    r["untimed"] = ((loc_mid.dt.hour == 0) & (loc_mid.dt.minute == 0)).astype(int)
    r["prio"] = r.source.map(SOURCE_PRIORITY).fillna(9)
    r = r.sort_values(["grp", "untimed", "prio"]).drop_duplicates("grp", keep="first")
    return r.drop(columns=["grp", "untimed", "prio"]).sort_values(["symbol", "ts_utc"]).reset_index(drop=True)


def build_events(panel: Panel, raw: pd.DataFrame) -> pd.DataFrame:
    """Past (and future) earnings stamps -> sessions and reactions, per name.

    raw: symbol, ts_utc, source. Output columns: symbol, ci, ts_utc, timing, pre_i, react_i,
    pre_date, react_date, r_c2c (close pre -> close react), r_o2o (open pre -> open react),
    absr, n_prior, trail_abs (mean |r_c2c| of the previous TRAIL_N reactions, >= MIN_PRIOR),
    on_cadence, market.
    """
    raw = dedupe_stamps(raw[raw.symbol.isin(panel.col)])
    out = []
    for sym, g in raw.groupby("symbol"):
        j = panel.col[sym]
        live = np.isfinite(panel.close[:, j])
        sess_i = np.flatnonzero(live)
        if len(sess_i) < 30:
            continue
        sess = panel.dates[sess_i]
        first_bar = sess[0]
        seen = set()
        for r in g.sort_values("ts_utc").itertuples():
            # a stamp before the name's first bar belongs to whatever traded under the ticker
            # before (a reused ticker's old company, cut by contest_calendar.cut_stitched)
            if pd.Timestamp(r.ts_utc).tz_convert(None).normalize() < first_bar:
                continue
            pre, react, timing = cc.event_sessions(r.ts_utc, sym, sess)
            loc_day = pd.Timestamp(pd.Timestamp(r.ts_utc).tz_convert(cc.session_hours(sym)[0]).date())
            if react >= len(sess) and loc_day > sess[-1]:
                # the report falls after the name's last bar: a FUTURE event. The last bar is
                # not "the session before the report", so no buy session is taken from bars;
                # the live desk assigns it by weekday in extend_future_sessions.
                pre = -1
            key = react if react < len(sess) else ("future", loc_day)   # two future reports stay two
            if key in seen:
                continue
            seen.add(key)
            row = {"symbol": sym, "ci": j, "ts_utc": r.ts_utc, "timing": timing,
                   "source": getattr(r, "source", ""), "market": panel.market[j]}
            if 0 <= pre < len(sess):
                row["pre_i"] = int(sess_i[pre])
                row["pre_date"] = sess[pre]
            if 0 <= react < len(sess):
                row["react_i"] = int(sess_i[react])
                row["react_date"] = sess[react]
            out.append(row)
    ev = pd.DataFrame(out)
    if ev.empty:
        return ev
    for col, na in (("pre_i", np.nan), ("react_i", np.nan), ("pre_date", pd.NaT), ("react_date", pd.NaT)):
        if col not in ev.columns:
            ev[col] = na
    has = ev.pre_i.notna() & ev.react_i.notna()
    pi = ev.loc[has, "pre_i"].astype(int).to_numpy()
    ri = ev.loc[has, "react_i"].astype(int).to_numpy()
    ci = ev.loc[has, "ci"].astype(int).to_numpy()
    ev.loc[has, "r_c2c"] = panel.close[ri, ci] / panel.close[pi, ci] - 1
    ev.loc[has, "r_o2o"] = panel.open[ri, ci] / panel.open[pi, ci] - 1
    bad = (ev.r_c2c > 2.0) | (ev.r_c2c < -0.8)            # splits / data faults
    ev.loc[bad, ["r_c2c", "r_o2o"]] = np.nan
    ev["absr"] = ev.r_c2c.abs()
    ev = ev.sort_values(["symbol", "ts_utc"]).reset_index(drop=True)
    ev["prev_react"] = ev.groupby("symbol").react_i.shift(1)
    gap = ev.react_i - ev.prev_react
    ev["on_cadence"] = np.where(ev.market == "US", gap.between(50, 80), gap >= 40)
    ev["n_prior"] = ev.groupby("symbol").absr.transform(lambda s: s.shift(1).notna().cumsum())
    ev["trail_abs"] = ev.groupby("symbol").absr.transform(
        lambda s: s.shift(1).rolling(TRAIL_N, min_periods=MIN_PRIOR).mean())
    return ev


def raw_event_stamps(*, asof: Optional[date] = None) -> pd.DataFrame:
    """US: SEC 8-K 2.02 (primary). Elsewhere: Yahoo earnings dates (vendor)."""
    us = cc.us_8k_events(asof)
    frames = [us]
    if cc.HIST_PATH.exists():
        h = pd.read_parquet(cc.HIST_PATH)
        h = h[h.symbol.map(cc.market_of) != "US"]
        if asof is not None:
            h = h[pd.to_datetime(h.ts_utc, utc=True).dt.date <= asof]
        # a past row without a reported EPS may be a vendor placeholder; keep rows that
        # reported, plus future rows (they are the calendar, not history)
        now = pd.Timestamp.now(tz="UTC")
        keep = pd.Series(True, index=h.index)   # past vendor rows are events; future rows are the calendar
        frames.append(h.loc[keep, ["symbol", "ts_utc", "source"]])
    if cc.HIST_US_PATH.exists() and len(us):
        # US stamps AFTER the SEC file ends (it is refreshed by another job, not this one)
        h = pd.read_parquet(cc.HIST_US_PATH)
        h["ts_utc"] = pd.to_datetime(h.ts_utc, utc=True)
        h = h[h.ts_utc > us.ts_utc.max() + pd.Timedelta(days=2)]
        if asof is not None:
            h = h[h.ts_utc.dt.date <= asof]
        frames.append(h[["symbol", "ts_utc", "source"]])
    return pd.concat(frames, ignore_index=True)


# ───────────────────────────── ranking ─────────────────────────────

def rank_candidates(cands: pd.DataFrame, *, liq_floor: float = cc.LIQ_FLOOR_USD,
                    min_prior: int = MIN_PRIOR, k: int = K_SLOTS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score = trailing mean |earnings reaction|. Returns (ranked eligible, refused-with-reason).

    cands needs: symbol, trail_abs, n_prior, dv63, price_usd, has_bars, membership.
    A name NOT_IN_WLS_EXPORT is refused; UNCONFIRMED_MEMBERSHIP is kept and labelled.
    """
    c = cands.copy()
    reason = pd.Series("", index=c.index, dtype=object)
    reason[~c["has_bars"].astype(bool)] = "REFUSED_NO_BARS"
    reason[(reason == "") & ~(c["dv63"].fillna(0) >= liq_floor)] = \
        f"REFUSED_ILLIQUID (median $vol < ${liq_floor / 1e6:.0f}M)"
    reason[(reason == "") & ~(c["price_usd"].fillna(0) >= MIN_PRICE_USD)] = "REFUSED_PRICE_BELOW_$1"
    reason[(reason == "") & ~(c["n_prior"].fillna(0) >= min_prior)] = \
        f"REFUSED_HISTORY (< {min_prior} past reactions)"
    reason[(reason == "") & ~c["trail_abs"].notna()] = "REFUSED_HISTORY (no reaction data)"
    if "membership" in c.columns:
        reason[(reason == "") & (c["membership"] == "NOT_IN_WLS_EXPORT")] = "REFUSED_NOT_IN_WLS"
    c["refusal"] = reason
    ok = c[c.refusal == ""].sort_values("trail_abs", ascending=False).reset_index(drop=True)
    ok["rank"] = np.arange(1, len(ok) + 1)
    ok["weight"] = np.where(ok["rank"] <= k, WEIGHT, 0.0)
    check_weights(ok["weight"].to_numpy())
    return ok, c[c.refusal != ""].reset_index(drop=True)


def check_weights(w: np.ndarray) -> None:
    w = np.asarray(w, dtype=float)
    if (w < -1e-12).any():
        raise SheetRefused("negative weight: long only")
    if (w > cc.POSITION_CAP + 1e-9).any():
        raise SheetRefused(f"weight above the {cc.POSITION_CAP:.0%} cap")
    if w.sum() > 1 + 1e-9:
        raise SheetRefused(f"weights sum to {w.sum():.4f} > 1 (no leverage)")


# ───────────────────────────── experimental columns (UNTESTED) ─────────────────────────────

def revision_trend(symbols: Iterable[str], asof: date) -> dict:
    """EXPERIMENTAL, UNTESTED: (current - 30d ago) / |30d ago| of the current-quarter EPS estimate."""
    p = cc.OPT / "analyst" / "eps_trend_snapshots.parquet"
    if not p.exists():
        return {}
    d = pd.read_parquet(p, columns=["ticker", "observed_at", "period", "current", "d30"])
    d = d[(d.period == "0q") & d.ticker.isin(set(symbols))]
    d = d[pd.to_datetime(d.observed_at, utc=True).dt.date <= asof]
    if d.empty:
        return {}
    d = d.sort_values("observed_at").groupby("ticker").tail(1)
    val = (d["current"] - d["d30"]) / d["d30"].abs().replace(0, np.nan)
    val = val.where(val.abs() <= 1.0)       # a near-zero base makes the ratio meaningless: n/a
    return dict(zip(d.ticker, val.round(4)))


def nn_lab_prob(symbols: Iterable[str], asof: date) -> dict:
    """EXPERIMENTAL, UNTESTED: nn_lab's latest `prob` for the name, decision date <= asof.

    Reads nn_lab's output files only (its code is not imported)."""
    files = sorted(glob.glob(str(cc.OPT / "nn_lab" / "predictions" / "pred_*.parquet")))
    best = None
    for f in files:
        dd = Path(f).name.split("_")[1]
        try:
            if date.fromisoformat(dd) <= asof:
                best = f
        except ValueError:
            continue
    if best is None:
        return {}
    d = pd.read_parquet(best, columns=["symbol", "horizon", "prob", "decision_date"])
    d = d[d.symbol.isin(set(symbols))].sort_values("horizon").groupby("symbol").head(1)
    return dict(zip(d.symbol, d.prob.round(3)))


NN_SIZE_DIR = cc.OPT / "nn_lab" / "size_forecast"


def nn_size_forecast(symbols: Iterable[str], asof: date, *,
                     folder: Optional[Path] = None) -> tuple[pd.DataFrame, Optional[str]]:
    """nn_lab's nightly SIZE-OF-MOVE forecast (ridge on |excess move|, conformal intervals),
    read from its frozen file `size_<decision_date>.parquet` -- nn_lab code is never imported.

    Uses the newest file whose decision date is STRICTLY before `asof` (the sheet uses bars
    before its own date). Returns (frame indexed by symbol with nn_size_5d, nn_size_21d,
    nn_hi90_5d, the file name). It predicts the SIZE of a 5- or 21-session excess move, not
    its direction, and not the earnings reaction itself. Displayed; it does not re-rank.
    """
    folder = Path(folder) if folder else NN_SIZE_DIR
    best, best_d = None, None
    for f in sorted(folder.glob("size_*.parquet")) if folder.exists() else []:
        try:
            dd = date.fromisoformat(f.stem.split("_", 1)[1])
        except ValueError:
            continue
        if dd < asof and (best_d is None or dd > best_d):
            best, best_d = f, dd
    empty = pd.DataFrame(columns=["nn_size_5d", "nn_size_21d", "nn_hi90_5d"])
    if best is None:
        return empty, None
    cols = ["ticker", "exp_abs_move_5", "exp_abs_move_21", "hi90_5"]
    d = pd.read_parquet(best, columns=cols)
    d = d[d.ticker.astype(str).str.upper().isin({str(s).upper() for s in symbols})]
    d = d.rename(columns={"exp_abs_move_5": "nn_size_5d", "exp_abs_move_21": "nn_size_21d",
                          "hi90_5": "nn_hi90_5d"})
    d["ticker"] = d.ticker.astype(str).str.upper()
    return d.drop_duplicates("ticker").set_index("ticker")[["nn_size_5d", "nn_size_21d", "nn_hi90_5d"]], best.name


def implied_move(symbol: str, react_date: date) -> Optional[float]:
    """ATM straddle mid / spot for the first expiry on/after the reaction (US listed options)."""
    try:
        import yfinance as yf                                   # noqa: PLC0415
        tk = yf.Ticker(symbol)
        exps = [e for e in tk.options if date.fromisoformat(e) >= react_date]
        if not exps:
            return None
        ch = tk.option_chain(exps[0])
        spot = float(tk.fast_info["last_price"])
        calls = ch.calls.assign(d=(ch.calls.strike - spot).abs()).sort_values("d")
        puts = ch.puts.assign(d=(ch.puts.strike - spot).abs()).sort_values("d")
        c0, p0 = calls.iloc[0], puts.iloc[0]
        mid = lambda r: (r.bid + r.ask) / 2 if (r.bid > 0 and r.ask > 0) else r.lastPrice  # noqa: E731
        return round(float((mid(c0) + mid(p0)) / spot), 4)
    except Exception:                                           # noqa: BLE001
        return None


# ───────────────────────────── the sheet ─────────────────────────────

def sheet_window(d: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[d 14:00 HKT, d+1 14:00 HKT): Europe d, US d, and Asia d+1 open inside it."""
    s = pd.Timestamp(datetime(d.year, d.month, d.day, SHEET_HOUR_HKT, 0), tz=cc.HKT)
    return s, s + pd.Timedelta(days=1)


def session_open_hkt(symbol: str, local_day: pd.Timestamp) -> pd.Timestamp:
    tz, o, _ = cc.session_hours(symbol)
    h, m = map(int, o.split(":"))
    return pd.Timestamp(datetime(local_day.year, local_day.month, local_day.day, h, m),
                        tz=tz).tz_convert(cc.HKT)


def candidates_for_sheet(d: date, events: pd.DataFrame, panel: Panel,
                         universe: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Events whose BUY session (the last session before the report) opens in the sheet's
    window. Uses only bars dated before the buy session and reactions that happened
    before the sheet date."""
    w0, w1 = sheet_window(d)
    rows = []
    ev_future = events[events.pre_date.notna()]
    lo = pd.Timestamp(d) - pd.Timedelta(days=1)
    hi = pd.Timestamp(d) + pd.Timedelta(days=3)
    for r in ev_future[(ev_future.pre_date >= lo) & (ev_future.pre_date <= hi)].itertuples():
        t_open = session_open_hkt(r.symbol, r.pre_date)
        if not (w0 <= t_open < w1):
            continue
        rows.append(r)
    if not rows:
        return pd.DataFrame()
    c = pd.DataFrame(rows).drop_duplicates("symbol", keep="first")
    # PIT features: trailing |reaction| from events that REACTED before the sheet date
    past = events[(events.react_date < pd.Timestamp(d)) & events.absr.notna()]
    tr = past.sort_values("react_date").groupby("symbol").absr.apply(lambda s: s.tail(TRAIL_N))
    trail = tr.groupby(level=0).agg(["mean", "size"]) if len(tr) else pd.DataFrame(columns=["mean", "size"])
    c["trail_abs"] = c.symbol.map(trail["mean"]).where(c.symbol.map(trail["size"]) >= MIN_PRIOR)
    c["n_prior"] = c.symbol.map(trail["size"]).fillna(0)
    i_asof = panel.idx(pd.Timestamp(d) - pd.Timedelta(days=1))  # last bar strictly before the sheet date
    ci = c.ci.astype(int).to_numpy()
    c["dv63"] = panel.dv63[i_asof, ci]
    c["sig63"] = panel.sig63[i_asof, ci]
    last_close = pd.DataFrame(panel.close[: i_asof + 1, :][:, ci]).ffill().iloc[-1].to_numpy()
    c["price_usd"] = last_close
    c["has_bars"] = np.isfinite(last_close)
    lo20 = max(0, i_asof - 30)
    px20 = pd.DataFrame(panel.close[lo20: i_asof + 1, :][:, ci]).dropna(how="all")
    c["drift20_EXPERIMENTAL"] = (px20.ffill().iloc[-1].to_numpy() / px20.bfill().iloc[0].to_numpy() - 1) \
        if len(px20) else np.nan
    if universe is not None:
        u = universe.set_index("symbol")
        for col in ("name", "bbg_ticker", "membership"):
            c[col] = c.symbol.map(u[col]) if col in u.columns else None
    else:
        c["membership"] = "UNCONFIRMED_MEMBERSHIP"
        c["bbg_ticker"] = c.symbol.map(cc.bloomberg_ticker)
    c["bbg_ticker"] = c["bbg_ticker"].fillna(c.symbol.map(cc.bloomberg_ticker))
    c["membership"] = c["membership"].fillna("UNCONFIRMED_MEMBERSHIP")
    c["buy_open_hkt"] = [session_open_hkt(s, p) for s, p in zip(c.symbol, c.pre_date)]
    return c


@dataclass
class Sheet:
    day: date
    buys: pd.DataFrame
    refused: pd.DataFrame
    sells: pd.DataFrame
    notes: list


def make_sheet(d: date, events: pd.DataFrame, panel: Panel, universe: Optional[pd.DataFrame],
               *, holdings: Optional[pd.DataFrame] = None, live: bool = False,
               calendar: Optional[pd.DataFrame] = None) -> Sheet:
    c = candidates_for_sheet(d, events, panel, universe)
    notes = []
    if c.empty:
        ranked, refused = pd.DataFrame(columns=["symbol", "weight", "rank"]), pd.DataFrame()
        notes.append("No name reports in this sheet's window: hold cash or the filler list.")
    else:
        # no information dated after the sheet date may enter a feature
        leak = c[c.react_date.notna() & (c.pre_date < pd.Timestamp(d) - pd.Timedelta(days=1))]
        if len(leak):
            raise SheetRefused(f"buy sessions before the sheet date: {leak.symbol.tolist()}")
        ranked, refused = rank_candidates(c)
        syms = ranked.symbol.head(15).tolist()
        rev = revision_trend(syms, d)
        nnp = nn_lab_prob(syms, d)
        ranked["revision30_EXPERIMENTAL"] = ranked.symbol.map(rev)
        ranked["nn_prob_EXPERIMENTAL"] = ranked.symbol.map(nnp)
        nns, nn_file = nn_size_forecast(ranked.symbol, d)
        for col in ("nn_size_5d", "nn_size_21d", "nn_hi90_5d"):
            ranked[col] = ranked.symbol.str.upper().map(nns[col]) if len(nns) else np.nan
        notes.append(f"NN size-of-move column: {nn_file or 'no nn_lab size file dated before this sheet'} "
                     "(US names only; size of a 5-session excess move, not direction; display only).")
        cut = cc.stitched_cut_symbols()
        ranked["stitched_cut"] = ranked.symbol.isin(cut)
        if ranked["stitched_cut"].any():
            notes.append("Reused tickers, history before the new company's first bar refused: "
                         + ", ".join(ranked.loc[ranked.stitched_cut, "symbol"].head(20)))
        if live:
            ranked["implied_move"] = [implied_move(s, rd.date()) if (i < 10 and cc.market_of(s) == "US"
                                      and pd.notna(rd)) else None
                                      for i, (s, rd) in enumerate(zip(ranked.symbol, ranked.react_date))]
        if calendar is not None and not calendar.empty:
            cal = calendar.set_index("symbol")
            ranked["date_status"] = ranked.symbol.map(cal["status"]).fillna("ESTIMATED_PATTERN")
            ranked["date_confirmed"] = ranked.symbol.map(cal["is_confirmed"]).fillna(False).astype(bool)
            ranked["date_sources"] = ranked.symbol.map(cal["sources"])
        else:
            ranked["date_status"] = "HISTORICAL_ACTUAL"
            ranked["date_confirmed"] = False
    sells = holdings if holdings is not None else pd.DataFrame(columns=["symbol"])
    return Sheet(d, ranked, refused, sells, notes)


def _fmt_pct(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if not np.isfinite(v) else f"{100 * v:.1f}%"


def render_sheet(s: Sheet, *, header_extra: str = "") -> tuple[str, str]:
    """(markdown, short text). Markets appear in the order they open in Hong Kong time."""
    w0, w1 = sheet_window(s.day)
    top = s.buys[s.buys.get("weight", pd.Series(dtype=float)) > 0] if len(s.buys) else s.buys
    nxt = s.buys[s.buys.get("weight", pd.Series(dtype=float)) == 0].head(5) if len(s.buys) else s.buys
    L = [f"# Contest sheet {s.day} (sessions opening {w0:%a %d %b %H:%M} to {w1:%a %d %b %H:%M} HKT)",
         "", f"*{LICENCE}* Zero directional skill is assumed: this rule sells variance for rank.",
         "Every name here is as likely to fall as to rise; the rule picks names that MOVE.", ""]
    if header_extra:
        L += [header_extra, ""]
    L += ["## 1. SELL (names whose report has happened)", ""]
    if s.sells is None or s.sells.empty:
        L.append("- nothing held from the previous sheet (or first day)")
    else:
        for r in s.sells.itertuples():
            L.append(f"- SELL **{getattr(r, 'bbg_ticker', r.symbol)}** ({r.symbol}) at its next session "
                     f"({getattr(r, 'react_date', '')})")
    L += ["", f"## 2. BUY: {len(top)} name(s) at 20% each, in Hong Kong opening order", ""]
    if len(top) == 0:
        L.append("- none eligible. Leave cash, or buy the filler list in section 3.")
    else:
        L.append("| # | Terminal ticker | name | market | buy session opens (HKT) | report | date status "
                 "| why ranked: avg abs move, last 8 | vol63 /day | NN size 5d | liquidity (median $/day) "
                 "| WLS membership | implied move |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in top.sort_values("buy_open_hkt").itertuples():
            conf = "CONFIRMED" if getattr(r, "date_confirmed", False) else f"NOT CONFIRMED ({r.date_status})"
            L.append(f"| {r.rank} | {r.bbg_ticker} | {str(getattr(r, 'name', '') or '')[:28]} | {r.market} "
                     f"| {r.buy_open_hkt:%a %H:%M} | {pd.Timestamp(r.ts_utc).tz_convert(cc.session_hours(r.symbol)[0]):%a %d %b %H:%M} local, {r.timing} "
                     f"| {conf} | {_fmt_pct(r.trail_abs)} over {int(r.n_prior)} "
                     f"| {_fmt_pct(getattr(r, 'sig63', None))} | {_fmt_pct(getattr(r, 'nn_size_5d', None))} "
                     f"| ${r.dv63 / 1e6:,.0f}M OK "
                     f"| {r.membership} | {_fmt_pct(getattr(r, 'implied_move', None))} |")
    L += ["", "## 3. If a name is not in the index or not tradable: take the next in rank", ""]
    if len(nxt):
        for r in nxt.itertuples():
            L.append(f"- #{r.rank} {r.bbg_ticker} ({r.market}, avg move {_fmt_pct(r.trail_abs)}, "
                     f"{r.membership})")
    else:
        L.append("- no reserve name in this window")
    if len(s.refused):
        L += ["", "Refused by name:", ""]
        for r in s.refused.head(25).itertuples():
            L.append(f"- {r.symbol}: {r.refusal}")
    L += ["", "## 4. Three checks on the Terminal before entering", "",
          "1. `EVTS` / `ERN` on each name: the report date and time match the column above "
          "(a NOT CONFIRMED date that moved means skip it and take the next in rank).",
          "2. `MEMB` of WLS Index (or the exported list): the name is a member; if not, next in rank.",
          "3. `TMSG`: cash available and each ticket at or under $200k / 20% (the cap rule's basis is unconfirmed).",
          ""]
    ex = [c for c in ("revision30_EXPERIMENTAL", "nn_prob_EXPERIMENTAL", "drift20_EXPERIMENTAL")
          if c in s.buys.columns]
    if len(top) and ex:
        L += ["## 5. Experimental columns (UNTESTED; they did not affect the ranking)", "",
              "| ticker | " + " | ".join(ex) + " |", "|---|" + "---|" * len(ex)]
        for r in top.itertuples():
            L.append(f"| {r.symbol} | " + " | ".join(
                "n/a" if pd.isna(getattr(r, c)) else f"{getattr(r, c):.3f}" for c in ex) + " |")
    for n in s.notes:
        L += ["", f"Note: {n}"]
    md = "\n".join(L) + "\n"
    short = [f"CONTEST {s.day}: SELL " + (", ".join(s.sells.symbol.astype(str)) if s.sells is not None
                                          and len(s.sells) else "none") + "."]
    short.append("BUY 20% each: " + (", ".join(f"{r.bbg_ticker} ({r.buy_open_hkt:%H:%M} HKT)"
                                              for r in top.sort_values("buy_open_hkt").itertuples())
                                     if len(top) else "none (cash)") + ".")
    if len(nxt):
        short.append("Reserves: " + ", ".join(nxt.bbg_ticker.head(3)) + ".")
    unconf = int((~top.date_confirmed).sum()) if len(top) and "date_confirmed" in top else 0
    short.append(f"{unconf} of {len(top)} dates NOT confirmed: check EVTS. Zero-skill lottery; not evidence.")
    return md, " ".join(short)


# ───────────────────────────── live refreshes ─────────────────────────────

IMPLIED_PATH = cc.CONTEST / "implied" / "implied_moves.parquet"


def snapshot_implied(calendar: pd.DataFrame, d: date, *, max_names: int = 80) -> dict:
    """Option-implied earnings moves for US names reporting in the next four sessions.

    Appended (never rewritten) to IMPLIED_PATH: the control variable the pre-registered
    magnitude trial needs, collected by the desk itself so the Terminal export is optional."""
    if calendar is None or calendar.empty:
        return {"n": 0}
    hi = pd.Timestamp(d) + pd.tseries.offsets.BDay(4)
    c = calendar[(calendar.market == "US") & (calendar.date >= pd.Timestamp(d)) & (calendar.date <= hi)]
    c = c.sort_values("adv_usd_3m", ascending=False).head(max_names)
    rows = []
    import time as _t                                           # noqa: PLC0415
    for r in c.itertuples():
        react = (r.date + pd.tseries.offsets.BDay(1)).date() if r.timing == "AMC" else r.date.date()
        im = implied_move(r.symbol, react)
        rows.append({"symbol": r.symbol, "asof_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "report_date": str(r.date.date()), "timing": r.timing, "date_status": r.status,
                     "implied_move": im, "source": "yahoo_options_atm_straddle"})
        _t.sleep(1.0)
    new = pd.DataFrame(rows)
    if new.empty:
        return {"n": 0}
    old = pd.read_parquet(IMPLIED_PATH) if IMPLIED_PATH.exists() else pd.DataFrame()
    allr = pd.concat([old, new], ignore_index=True) if not old.empty else new
    cc.safe_write_parquet(allr, IMPLIED_PATH)
    return {"n": int(len(new)), "n_with_value": int(new.implied_move.notna().sum())}


def refresh_bars_for(symbols: Iterable[str]) -> dict:
    """Top up bars for the names the sheet may rank (plus FX and the benchmark)."""
    by_m: dict[str, list] = {}
    for s in set(symbols):
        by_m.setdefault(cc.market_of(s), []).append(s)
    recs = {"FX": cc.pull_bars(sorted({t for t in cc.CCY_FX.values() if t}) + ["ACWI", "URTH", "SPY"],
                               "FX", start=str(date.today() - timedelta(days=120)))}
    for m, ss in by_m.items():
        recs[m] = cc.pull_bars(sorted(ss), m, start=str(date.today() - timedelta(days=120)))
    return {k: {kk: v.get(kk) for kk in ("n_symbols", "rows_after", "n_failed", "last_date")}
            for k, v in recs.items()}


def bars_age_lines(panel: Panel, d: date) -> list[str]:
    out = []
    for m in sorted(set(panel.market)):
        cols = np.flatnonzero(panel.market == m)
        live = np.isfinite(panel.close[:, cols]).any(axis=1)
        last = panel.dates[np.flatnonzero(live)[-1]].date() if live.any() else None
        age = (d - last).days if last else None
        flag = " STALE" if age is None or age > 4 else ""
        out.append(f"{m}: last bar {last} ({age} days){flag}")
    return out


def telegram_line(d: Optional[date] = None) -> str:
    """The one line the Telegram `report` reply can include (reads the file; sends nothing)."""
    d = d or date.today()
    f = SHEETS / f"{d}.txt"
    if not f.exists():
        return f"contest: no sheet for {d} (desk not run or STOP file present)"
    return f.read_text(encoding="utf-8").strip()


# ───────────────────────────── live CLI ─────────────────────────────

def run_live(d: date, *, refresh: bool = True, preview: bool = False) -> int:
    """The evening sheet. `preview` writes to contest/preview/ (never read as holdings)."""
    out_dir = PREVIEW if preview else SHEETS
    if STOP_FILE.exists():
        print(f"STOP file present ({STOP_FILE}); no sheet written.")
        return 0
    receipt: dict = {"day": str(d), "started_utc": cc.utc_stamp()}
    ufiles = sorted(cc.UNIV_DIR.glob("universe_*.parquet"))
    if refresh and (not ufiles or ufiles[-1].name < f"universe_{d - timedelta(days=7)}.parquet"):
        try:
            cc.cmd_universe()
            receipt["universe"] = "refreshed (weekly)"
        except Exception as exc:                                # noqa: BLE001
            receipt["universe"] = f"REFRESH FAILED {type(exc).__name__}: {exc}"
    if refresh:
        try:
            cc.cmd_calendar(d)
            receipt["calendar"] = "refreshed"
        except Exception as exc:                                # noqa: BLE001
            receipt["calendar"] = f"REFRESH FAILED {type(exc).__name__}: {exc} (using the last file)"
    universe = cc.latest_universe()
    cal_files = sorted(cc.CAL_DIR.glob("calendar_*.parquet"))
    calendar = pd.read_parquet(cal_files[-1]) if cal_files else pd.DataFrame()
    if refresh and not calendar.empty:
        soon = calendar[(calendar.date >= pd.Timestamp(d) - pd.Timedelta(days=3))
                        & (calendar.date <= pd.Timestamp(d) + pd.Timedelta(days=10))]
        held = []
        prevh = sorted(x for x in SHEETS.glob("*_holdings.json") if x.name < f"{d}_holdings.json")
        if prevh:
            held = [x["symbol"] for x in json.loads(prevh[-1].read_text(encoding="utf-8")).get("buys", [])]
        try:
            receipt["bars"] = refresh_bars_for(list(soon.symbol) + held)
        except Exception as exc:                                # noqa: BLE001
            receipt["bars"] = f"FAILED {type(exc).__name__}: {exc}"
        try:
            receipt["implied"] = snapshot_implied(calendar, d)
        except Exception as exc:                                # noqa: BLE001
            receipt["implied"] = f"FAILED {type(exc).__name__}: {exc}"
    panel = load_panel(start="2019-01-01")
    raw = raw_event_stamps()
    # the calendar's upcoming dates become future stamps (timing from the calendar)
    fut = []
    for r in calendar.itertuples():
        tz, o, c = cc.session_hours(r.symbol)
        hm = {"AMC": c, "BMO": "07:00", "INTRA": "12:00"}.get(r.timing)
        if hm is None:
            hm = c              # unknown timing: assume after the close (buy the session before)
        h, m = map(int, hm.split(":"))
        if r.timing == "AMC":
            m += 5
        ts = pd.Timestamp(datetime(r.date.year, r.date.month, r.date.day, h, min(m, 59)), tz=tz)
        fut.append({"symbol": r.symbol, "ts_utc": ts.tz_convert("UTC"), "source": r.status})
    if fut:
        raw = pd.concat([raw[raw.ts_utc < pd.Timestamp.now(tz="UTC")], pd.DataFrame(fut)], ignore_index=True)
    events = build_events(panel, raw)
    events = extend_future_sessions(events, panel, d)
    prev = sorted(x for x in SHEETS.glob("*_holdings.json") if x.name < f"{d}_holdings.json")
    holdings = None
    if prev:
        h = json.loads(prev[-1].read_text(encoding="utf-8"))
        holdings = pd.DataFrame(h.get("buys", []))
    sh = make_sheet(d, events, panel, universe, holdings=holdings, live=refresh, calendar=calendar)
    ages = bars_age_lines(panel, d)
    md, short = render_sheet(sh, header_extra=f"Calendar: {cal_files[-1].name if cal_files else 'NONE'}; "
                                              f"universe membership: "
                                              f"{'WLS export' if cc.load_wls_export() is not None else 'PROXY (unconfirmed)'}.  "
                                              f"Bars: " + "; ".join(ages))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{d}.md").write_text(md, encoding="utf-8")
    (out_dir / f"{d}.txt").write_text(short + "\n", encoding="utf-8")
    top = sh.buys[sh.buys.weight > 0] if len(sh.buys) else sh.buys
    cc.write_json({"day": str(d), "buys": [{"symbol": r.symbol, "bbg_ticker": r.bbg_ticker,
                                             "react_date": str(pd.Timestamp(r.react_date).date())
                                             if pd.notna(r.react_date) else None}
                                            for r in top.itertuples()]},
                  out_dir / f"{d}_holdings.json")
    receipt["n_buys"] = int(len(top))
    receipt["finished_utc"] = cc.utc_stamp()
    cc.write_json(receipt, out_dir / f"{d}_receipt.json")
    print(short)
    return 0


def extend_future_sessions(events: pd.DataFrame, panel: Panel, d: date) -> pd.DataFrame:
    """Future events have no bar yet for their buy/react sessions: assign them by weekday."""
    ev = events.copy()
    miss = ev.pre_date.isna() | ev.react_date.isna()
    fut = ev[miss & (pd.to_datetime(ev.ts_utc, utc=True) > pd.Timestamp(d - timedelta(days=3), tz="UTC"))]
    for i, r in fut.iterrows():
        tz, o, c = cc.session_hours(r.symbol)
        sess = pd.bdate_range(pd.Timestamp(d) - pd.Timedelta(days=10), pd.Timestamp(d) + pd.Timedelta(days=60))
        pre, react, timing = cc.event_sessions(r.ts_utc, r.symbol, sess)
        ev.at[i, "pre_date"] = sess[pre] if 0 <= pre < len(sess) else pd.NaT
        ev.at[i, "react_date"] = sess[react] if 0 <= react < len(sess) else pd.NaT
        ev.at[i, "timing"] = timing
    return ev


# ───────────────────────────── the dry run ─────────────────────────────

def nasdaq_stamps(d0: date, d1: date) -> pd.DataFrame:
    """US report stamps for past dates from Nasdaq's calendar (vendor), cached per day.

    The SEC 8-K file on disk ends 2026-09-03, so the dry run's US reports come from here.
    AMC -> 16:05 ET, BMO -> 07:00 ET, time not supplied -> midnight (a two-session hold)."""
    cache = cc.CAL_DIR / "nasdaq_days"
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for d in pd.bdate_range(d0, d1):
        f = cache / f"{d.date()}.parquet"
        if f.exists():
            nd = pd.read_parquet(f)
        else:
            try:
                nd = cc.fetch_nasdaq_day(d.date())
            except Exception as exc:                            # noqa: BLE001
                print(f"  nasdaq {d.date()}: {type(exc).__name__}", flush=True)
                continue
            if len(nd):
                nd.to_parquet(f, index=False)
        frames.append(nd)
    if not frames:
        return pd.DataFrame(columns=["symbol", "ts_utc", "source"])
    n = pd.concat(frames, ignore_index=True)
    hm = n.timing.map({"AMC": (16, 5), "BMO": (7, 0)})
    ts = []
    for dd, h in zip(n.date, hm):
        hh, mm = h if isinstance(h, tuple) else (0, 0)
        ts.append(pd.Timestamp(datetime(dd.year, dd.month, dd.day, hh, mm), tz="America/New_York").tz_convert("UTC"))
    return pd.DataFrame({"symbol": n.symbol, "ts_utc": ts, "source": "nasdaq_calendar"})


def dry_run(d0: date, d1: date, *, panel: Optional[Panel] = None, raw: Optional[pd.DataFrame] = None,
            universe: Optional[pd.DataFrame] = None, cost_bps: float = 25.0) -> dict:
    """Sheets for every weekday in [d0, d1] built from what was knowable then, scored after.

    The report dates are the ACTUAL dates (companies publish them 1-4 weeks ahead; the
    live desk shows them as CONFIRMED only when a primary source says so). A second pass
    uses only our PIT pattern estimates, which is what the desk knows with no vendor.
    """
    panel = panel or load_panel(start="2019-01-01")
    if raw is None:
        raw = raw_event_stamps()
        extra = nasdaq_stamps(d0 - timedelta(days=3), d1 + timedelta(days=7))
        raw = pd.concat([raw, extra], ignore_index=True)
    events = build_events(panel, raw)
    universe = universe if universe is not None else cc.latest_universe()
    DRY.mkdir(parents=True, exist_ok=True)
    days, results = pd.bdate_range(d0, d1), []
    for d in days:
        sh = make_sheet(d.date(), events, panel, universe)
        top = sh.buys[sh.buys.weight > 0] if len(sh.buys) else sh.buys
        md, short = render_sheet(sh, header_extra="DRY RUN on past dates: report dates are the actual "
                                                  "ones; features use only data before this date.")
        (DRY / f"{d.date()}.md").write_text(md, encoding="utf-8")
        row = {"day": str(d.date()), "n_candidates": int(len(sh.buys) + len(sh.refused)),
               "n_eligible": int(len(sh.buys)), "n_bought": int(len(top)), "names": []}
        for r in top.itertuples():
            scored = pd.notna(getattr(r, "r_c2c", np.nan))
            row["names"].append({"symbol": r.symbol, "market": r.market, "timing": r.timing,
                                 "trail_abs": round(float(r.trail_abs), 4),
                                 "r_close_fill": None if not scored else round(float(r.r_c2c), 4),
                                 "r_next_open_fill": None if pd.isna(r.r_o2o) else round(float(r.r_o2o), 4),
                                 "react_date": str(pd.Timestamp(r.react_date).date()) if pd.notna(r.react_date) else None})
        results.append(row)
    # score: each day's book = sum of 20% slots (cash earns 0), relative to ACWI over the same sessions
    bench = "ACWI" if "ACWI" in panel.col else ("SPY" if "SPY" in panel.col else None)
    out = {"window": [str(d0), str(d1)], "benchmark": bench, "days": results}
    for fill, key in (("close_before_report", "r_close_fill"), ("next_open", "r_next_open_fill"),
                      ("next_open_25bps", "r_next_open_fill")):
        nav, rows = 1.0, []
        for row in results:
            rs = [n[key] for n in row["names"] if n[key] is not None]
            if len(rs) < len(row["names"]):
                rows.append({"day": row["day"], "status": "UNSCORED (reaction not yet in the bars)"})
                continue
            cost = (2 * cost_bps / 1e4) if fill.endswith("bps") else 0.0
            day_r = sum(WEIGHT * (r - cost) for r in rs)
            nav *= 1 + day_r
            rows.append({"day": row["day"], "book_return": round(day_r, 4), "n": len(rs)})
        out[fill] = {"nav_end": round(nav, 4), "days": rows}
    if bench:
        j = panel.col[bench]
        i0, i1 = panel.idx(pd.Timestamp(d0) - pd.Timedelta(days=1)), panel.idx(pd.Timestamp(d1) + pd.Timedelta(days=3))
        cl = pd.Series(panel.close[i0: i1 + 1, j]).dropna()
        out["benchmark_return_window"] = round(float(cl.iloc[-1] / cl.iloc[0] - 1), 4) if len(cl) > 1 else None
    cc.write_json(out, DRY / f"dry_run_{d0}_{d1}.json")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Contest desk: the evening order sheet.")
    ap.add_argument("--date", default=None, help="'today' or YYYY-MM-DD")
    ap.add_argument("--dry-run", nargs=2, metavar=("FROM", "TO"))
    ap.add_argument("--no-refresh", action="store_true", help="skip network refreshes")
    ap.add_argument("--telegram-line", action="store_true", help="print the one-line summary and exit")
    ap.add_argument("--preview", action="store_true",
                    help="write to contest/preview/ (a look ahead; never read back as holdings)")
    a = ap.parse_args(argv)
    if a.telegram_line:
        print(telegram_line(None if a.date in (None, "today") else date.fromisoformat(a.date)))
        return 0
    if a.dry_run:
        res = dry_run(date.fromisoformat(a.dry_run[0]), date.fromisoformat(a.dry_run[1]))
        print(json.dumps({k: (v["nav_end"] if isinstance(v, dict) and "nav_end" in v else v)
                          for k, v in res.items() if k != "days"}, indent=1, default=str))
        return 0
    d = date.today() if a.date in (None, "today") else date.fromisoformat(a.date)
    return run_live(d, refresh=not a.no_refresh, preview=a.preview)


if __name__ == "__main__":
    raise SystemExit(main())
