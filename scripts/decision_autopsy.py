"""What happened to the names we bought, probed and refused? The decision autopsy.

    python -m scripts.decision_autopsy            # local bars only
    python -m scripts.decision_autopsy --fetch    # + fresh daily bars (Alpaca DATA endpoint)

For every row of `<OPTIMUS_LEDGER_DIR>/decisions/YYYY-MM-DD.json` carrying a
ticker and a direction (BUY / PROBE / REFUSED / WATCH / SELL), and every
`predictions.jsonl` row made since 2026-09-11, the realised 1/5/21-session
return RELATIVE TO TWO BENCHMARKS, entered at the OPEN of the first session
after the decision date and marked at the close `h` sessions later (the same
convention as `llm_portfolio.grade`). No cost is charged: this grades the
CALL, not a book.

TWO BENCHMARKS, AND WHICH ONE IS THE HEADLINE (2026-09-25, review row 9)
------------------------------------------------------------------------
SPY alone measured SIZE, not skill: a small/mid shortlist against a
cap-weighted index in a mega-cap week loses to SPY whatever the calls were.
Every table now prints, beside SPY, the TIME-MATCHED CROSS-SECTIONAL MEDIAN of
the funnel's own universe -- the names `xs_ranker.mark_eligible` admits on the
decision date, each entered at the same open and marked at the same close.
Median rather than mean for the reason `night_inflection_baserate.build_market`
records (the mean of a fat-tailed cross-section is what broke there). The
HEADLINE is the PROBE - REFUSED gap measured over that median, with n counted
in DATE BLOCKS as well as rows.

Printed: a table by direction and by day, the refused names that went up, the
bought names that went down, and the forecasts grouped by specialist. Receipt:
`decisions/autopsy_<date>.json`. A horizon that has not elapsed is PENDING and
counted as pending -- never as zero.

WHY THIS EXISTS
===============
The decision contract has written EXPLOIT / EXPLORE / PROBE / REFUSED rows every
day since 2026-09-20 and nothing has ever read what the refused names did. A
refusal is a forecast ("this is not worth owning"), and a forecast nobody grades
is an opinion.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                # noqa: E402

LEDGER = Path(_cfg.OPTIMUS_LEDGER_DIR)
DECISIONS_DIR = LEDGER / "decisions"
PREDICTIONS_PATH = LEDGER / "predictions.jsonl"
HORIZONS = (1, 5, 21)
PREDICTIONS_SINCE = "2026-09-11"
MARKET = "SPY"
UNIVERSE = "XS_MEDIAN"
#: Fewer eligible names with a complete window than this and the universe
#: median is not reported (a median of a dozen names is not "the universe").
MIN_UNIVERSE_NAMES = 200
#: Eligibility needs >= xs_ranker.MIN_HISTORY_SESSIONS (126) sessions of
#: history per name, so the universe panel is read from this far back.
UNIVERSE_HISTORY_START = "2025-01-01"
DIRECTIONS = ("BUY", "PROBE", "REFUSED", "WATCH", "SELL")


# ─────────────────────────────── inputs ─────────────────────────────────────

def load_decisions(folder: Path = DECISIONS_DIR, skipped: dict | None = None) -> list[dict]:
    """One row per (decision day, ticker, direction). PROBE rows are virtual and
    repeat per horizon, so they are de-duplicated: the autopsy grades the NAME
    call on a day, and its own 1/5/21 horizons replace the probe's.

    A row whose `instrument_kind` is not a single name (the agency's
    `AGENCY_BOOK:<personality>` rows carry `instrument_kind: "book"`) is not a
    ticker and has no bar; it is COUNTED into `skipped` as `<kind>:<direction>`
    instead of being graded as an UNPRICED BUY."""
    out, seen = [], set()
    pat = "20[0-9][0-9]-[01][0-9]-[0-3][0-9].json"
    # `pc_plan/` = `sim_run.u_plan`'s PROBE rows (chunk C3): paper ORDERS, not
    # virtual rows, so they carry their own `origin` and are not de-duplicated
    # against the contract's virtual PROBE row for the same name and day.
    files = ([(f, "contract") for f in sorted(folder.glob(pat))]
             + [(f, "pc_plan") for f in sorted((folder / "pc_plan").glob(pat))])
    for f, origin in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        day = str(d.get("date") or f.stem)
        for r in d.get("rows") or []:
            t = str(r.get("ticker") or "").strip().upper()
            direction = str(r.get("direction") or "").strip().upper()
            if not t or direction not in DIRECTIONS:
                continue
            kind = r.get("instrument_kind")
            if kind not in (None, "", "equity", "stock", "etf"):
                if skipped is not None:
                    k = f"{kind}:{direction}"
                    skipped[k] = skipped.get(k, 0) + 1
                continue
            key = (day, t, direction, origin)
            if key in seen:
                continue
            seen.add(key)
            out.append({"date": day, "ticker": t, "direction": direction,
                        "terminal_state": r.get("terminal_state"),
                        "authority": r.get("authority"),
                        "refusal_class": r.get("refusal_class"),
                        "signal": r.get("signal"),
                        "decision_id": r.get("decision_id"),
                        "origin": origin})
    return out


def load_predictions(path: Path = PREDICTIONS_PATH, since: str = PREDICTIONS_SINCE) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        made = str(r.get("made_at") or "")[:10]
        if made < since or not r.get("ticker"):
            continue
        out.append({"date": str(r.get("decision_date") or made)[:10], "made_at": made,
                    "ticker": str(r["ticker"]).upper(),
                    "specialist": r.get("specialist"), "observable": r.get("observable"),
                    "horizon_days": r.get("horizon_days"), "probability": r.get("probability"),
                    "prediction_id": r.get("prediction_id")})
    return out


# ─────────────────────────────── returns ────────────────────────────────────

def eligibility(bars: pd.DataFrame) -> pd.DataFrame:
    """(symbol, date, eligible) under `xs_ranker.mark_eligible`, trailing data only.

    Computes ONLY the three columns `mark_eligible` reads (`vol_63`, `mom_63`,
    `median_dollar_vol`), with the same windows `xs_ranker.build_features`
    uses, rather than the full 24-feature build: the rule is reused verbatim,
    the cost is not paid for features nothing here reads.
    """
    import math
    from backend.services import xs_ranker as XR
    df = (bars[["symbol", "date", "close", "volume"]].dropna(subset=["close"])
          .sort_values(["symbol", "date"]).reset_index(drop=True).copy())
    df["date"] = pd.to_datetime(df["date"])
    g = df.groupby("symbol", sort=False)
    df["ret_1"] = g["close"].pct_change(fill_method=None)
    df["mom_63"] = g["close"].pct_change(63, fill_method=None)
    df["vol_63"] = (df.groupby("symbol", sort=False)["ret_1"]
                    .transform(lambda x: x.rolling(63, min_periods=40).std()) * math.sqrt(252))
    df["dollar_vol"] = df["close"] * df["volume"]
    df["median_dollar_vol"] = (df.groupby("symbol", sort=False)["dollar_vol"]
                               .transform(lambda x: x.rolling(63, min_periods=40).median()))
    return XR.mark_eligible(df)[["symbol", "date", "eligible"]]


class UniverseMedian:
    """The time-matched cross-sectional MEDIAN return of the eligible universe.

    `window(entry, exit, asof)` = median over names eligible on the last panel
    date <= `asof` of close[exit] / open[entry] - 1. A name with no bar on
    either date is left out of that window (not zeroed). Eligibility is read
    from the panel as of the decision, so a name that became eligible later
    cannot enter an earlier benchmark.
    """

    def __init__(self, bars: pd.DataFrame, elig: pd.DataFrame, *,
                 min_names: int = MIN_UNIVERSE_NAMES):
        b = bars.dropna(subset=["open", "close"]).copy()
        b["date"] = pd.to_datetime(b["date"])
        self.open = b.pivot_table(index="date", columns="symbol", values="open", aggfunc="first")
        self.close = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="first")
        e = elig[elig["eligible"].astype(bool)].copy()
        e["date"] = pd.to_datetime(e["date"])
        self.elig_by_date = {d: set(g["symbol"]) for d, g in e.groupby("date")}
        self.elig_dates = np.array(sorted(self.elig_by_date), dtype="datetime64[ns]")
        self.min_names = int(min_names)
        self._cache: dict = {}

    def window(self, entry, exit_, asof) -> dict | None:
        key = (str(entry), str(exit_), str(asof))
        if key in self._cache:
            return self._cache[key]
        out = None
        k = int(np.searchsorted(self.elig_dates, np.datetime64(pd.Timestamp(asof), "ns"),
                                side="right")) - 1
        t0, t1 = pd.Timestamp(entry), pd.Timestamp(exit_)
        if k >= 0 and t0 in self.open.index and t1 in self.close.index:
            e_date = pd.Timestamp(self.elig_dates[k])
            cols = sorted(c for c in self.elig_by_date[e_date] if c in self.open.columns)
            o = self.open.loc[t0, cols].to_numpy(float)
            c = self.close.loc[t1, cols].to_numpy(float)
            ok = np.isfinite(o) & np.isfinite(c) & (o > 0)
            r = c[ok] / o[ok] - 1.0
            if len(r) >= self.min_names:
                out = {"median": float(np.median(r)), "n": int(len(r)),
                       "n_eligible": len(cols), "eligible_asof": str(e_date.date())}
        self._cache[key] = out
        return out


class Prices:
    """Per-symbol (dates, open, close) arrays, built once.

    `universe` (optional) adds the second benchmark to every graded window:
    `univ` (the eligible cross-section's median) and `rel_univ = ret - univ`.
    """

    def __init__(self, bars: pd.DataFrame, universe: UniverseMedian | None = None):
        self.universe = universe
        b = bars.dropna(subset=["open", "close"]).sort_values(["symbol", "date"])
        self.px = {s: (g["date"].values.astype("datetime64[ns]"),
                       g["open"].to_numpy(float), g["close"].to_numpy(float))
                   for s, g in b.groupby("symbol", sort=False)}
        m = self.px.get(MARKET)
        self.sessions = m[0] if m is not None else np.array([], dtype="datetime64[ns]")
        self.last_session = str(pd.Timestamp(self.sessions[-1]).date()) if len(self.sessions) else None

    def _leg(self, sym: str, i0: np.datetime64, i1: np.datetime64) -> float | None:
        p = self.px.get(sym)
        if p is None:
            return None
        d, o, c = p
        a = int(np.searchsorted(d, i0, side="left"))
        b = int(np.searchsorted(d, i1, side="right")) - 1
        if a >= len(d) or d[a] != i0 or b < a or d[b] != i1 or o[a] <= 0:
            return None
        return float(c[b] / o[a] - 1.0)

    def relative(self, ticker: str, asof: str, horizons: Iterable[int] = HORIZONS) -> dict:
        """{h: {'status', 'rel', 'ret', 'spy'}}. PENDING until h sessions exist."""
        out = {}
        s = self.sessions
        i0 = int(np.searchsorted(s, np.datetime64(pd.Timestamp(asof), "ns"), side="right"))
        for h in horizons:
            i1 = i0 + int(h) - 1
            if i1 >= len(s):
                out[h] = {"status": "PENDING", "needs_session": int(h), "has": int(max(0, len(s) - i0))}
                continue
            r = self._leg(ticker, s[i0], s[i1])
            m = self._leg(MARKET, s[i0], s[i1])
            if r is None or m is None:
                out[h] = {"status": "UNPRICED"}
                continue
            u = (self.universe.window(pd.Timestamp(s[i0]), pd.Timestamp(s[i1]), asof)
                 if self.universe is not None else None)
            out[h] = {"status": "OK", "ret": r, "spy": m, "rel": r - m,
                      "univ": u["median"] if u else None,
                      "rel_univ": (r - u["median"]) if u else None,
                      "univ_n": u["n"] if u else None,
                      "entry": str(pd.Timestamp(s[i0]).date()),
                      "exit": str(pd.Timestamp(s[i1]).date())}
        return out


# ─────────────────────────────── autopsy ────────────────────────────────────

def _summ(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "mean_rel": None, "median_rel": None, "share_up": None}
    a = np.array(vals, float)
    return {"n": int(len(a)), "mean_rel": float(a.mean()), "median_rel": float(np.median(a)),
            "share_up": float((a > 0).mean())}


def _summ2(xs: list[dict]) -> dict:
    """`_summ` vs SPY (keys unchanged) + the same vs the universe median
    (`*_univ`) + the two benchmarks' own mean returns over the same rows."""
    out = _summ([x["rel"] for x in xs])
    u = [x for x in xs if x.get("rel_univ") is not None]
    su = _summ([x["rel_univ"] for x in u])
    out.update({"n_univ": su["n"], "mean_rel_univ": su["mean_rel"],
                "median_rel_univ": su["median_rel"], "share_up_univ": su["share_up"],
                "mean_spy": float(np.mean([x["spy"] for x in xs])) if xs else None,
                "mean_univ": float(np.mean([x["univ"] for x in u])) if u else None})
    return out


def _mean(v: list[float]) -> float | None:
    return float(np.mean(v)) if v else None


def gap(graded: list[dict], horizons: Iterable[int], a: str = "PROBE",
        b: str = "REFUSED") -> dict:
    """THE HEADLINE: `a` minus `b`, per horizon, over both benchmarks.

    `pooled_*` = mean(a) - mean(b) over all rows. `day_matched` = the mean over
    decision days carrying BOTH directions of (day mean a - day mean b): every
    row on one day shares one window, so the benchmark cancels inside a day and
    this number is benchmark-free; it is the one that cannot be a day-mix
    artefact. n is reported in DATE BLOCKS beside rows (review 2.5).
    """
    out = {}
    for h in horizons:
        rows = {d: [g["rel"][h] for g in graded
                    if g["direction"] == d and g["rel"][h].get("status") == "OK"]
                for d in (a, b)}
        ru = {d: [x["rel_univ"] for x in rows[d] if x.get("rel_univ") is not None] for d in rows}
        rs = {d: [x["rel"] for x in rows[d]] for d in rows}
        per_day: dict = {}
        for g in graded:
            x = g["rel"][h]
            if g["direction"] in (a, b) and x.get("status") == "OK":
                per_day.setdefault(g["date"], {}).setdefault(g["direction"], []).append(x["ret"])
        both = {d: float(np.mean(v[a]) - np.mean(v[b]))
                for d, v in sorted(per_day.items()) if a in v and b in v}
        dm = np.array(list(both.values()), float)
        pu = (_mean(ru[a]) - _mean(ru[b])) if ru[a] and ru[b] else None
        ps = (_mean(rs[a]) - _mean(rs[b])) if rs[a] and rs[b] else None
        out[str(h)] = {
            "pair": f"{a}-{b}",
            "pooled_vs_universe_median": pu,
            "pooled_vs_spy": ps,
            f"n_rows_{a}": len(ru[a]), f"n_rows_{b}": len(ru[b]),
            f"n_rows_{a}_spy": len(rs[a]), f"n_rows_{b}_spy": len(rs[b]),
            "n_date_blocks": len(both),
            "day_matched_gap": float(dm.mean()) if len(dm) else None,
            "day_matched_t": (float(dm.mean() / (dm.std(ddof=1) / np.sqrt(len(dm))))
                              if len(dm) >= 3 and dm.std(ddof=1) > 0 else None),
            "day_matched_by_day": both,
        }
    return out


def _longest(rel: dict) -> tuple[int | None, float | None]:
    for h in sorted(rel, reverse=True):
        if rel[h].get("status") == "OK":
            return h, rel[h]["rel"]
    return None, None


def autopsy(decisions: list[dict], predictions: list[dict], prices: Prices,
            horizons: Iterable[int] = HORIZONS) -> dict:
    horizons = tuple(int(h) for h in horizons)
    graded = []
    for r in decisions:
        g = dict(r)
        g["rel"] = prices.relative(r["ticker"], r["date"], horizons)
        graded.append(g)

    by_dir, by_day = {}, {}
    status = {}
    bench_day: dict = {}
    for g in graded:
        for h in horizons:
            x = g["rel"][h]
            status.setdefault(g["direction"], {}).setdefault(str(h), {}).setdefault(x["status"], 0)
            status[g["direction"]][str(h)][x["status"]] += 1
            if x["status"] != "OK":
                continue
            by_dir.setdefault(g["direction"], {}).setdefault(h, []).append(x)
            by_day.setdefault(g["date"], {}).setdefault(g["direction"], {}).setdefault(h, []).append(x)
            bench_day.setdefault(g["date"], {})[str(h)] = {
                "entry": x.get("entry"), "exit": x.get("exit"), "spy": x.get("spy"),
                "universe_median": x.get("univ"), "universe_n": x.get("univ_n")}

    table_dir = {d: {str(h): _summ2(by_dir.get(d, {}).get(h, [])) for h in horizons}
                 for d in sorted({g["direction"] for g in graded})}
    table_day = {day: {d: {str(h): _summ2(v.get(h, [])) for h in horizons} for d, v in dd.items()}
                 for day, dd in sorted(by_day.items())}

    def _list(direction: str, sign: int) -> list[dict]:
        rows = []
        for g in graded:
            if g["direction"] != direction:
                continue
            h, rel = _longest(g["rel"])
            if rel is None or np.sign(rel) != sign:
                continue
            rows.append({"date": g["date"], "ticker": g["ticker"], "horizon": h,
                         "rel": rel, "rel_univ": g["rel"][h].get("rel_univ"),
                         "terminal_state": g.get("terminal_state"),
                         "refusal_class": g.get("refusal_class"), "signal": g.get("signal")})
        return sorted(rows, key=lambda r: -sign * r["rel"])

    # forecasts, by specialist
    spec = {}
    pred_rows = []
    for p in predictions:
        rel = prices.relative(p["ticker"], p["date"], horizons)
        own = p.get("horizon_days")
        own_x = rel.get(int(own)) if own in horizons else None
        row = {**p, "rel": {str(h): rel[h].get("rel") for h in horizons},
               "rel_univ": {str(h): rel[h].get("rel_univ") for h in horizons},
               "status": {str(h): rel[h]["status"] for h in horizons}}
        if own_x is not None and own_x.get("status") == "OK" and p.get("probability") is not None:
            outcome = 1.0 if own_x["rel"] > 0 else 0.0
            row["own_horizon_outcome_beat_spy"] = outcome
            row["own_horizon_brier"] = (float(p["probability"]) - outcome) ** 2
            row["own_horizon_call_right"] = bool((float(p["probability"]) > 0.5) == (outcome == 1.0))
        pred_rows.append(row)
        s = spec.setdefault(p.get("specialist") or "?", {"rows": []})
        s["rows"].append(row)
    spec_table = {}
    for name, s in spec.items():
        rows = s["rows"]
        graded_own = [r for r in rows if "own_horizon_brier" in r]
        spec_table[name] = {
            "n": len(rows),
            "by_horizon": {str(h): _summ([r["rel"][str(h)] for r in rows
                                          if r["rel"][str(h)] is not None]) for h in horizons},
            "by_horizon_vs_universe": {str(h): _summ([r["rel_univ"][str(h)] for r in rows
                                                      if r["rel_univ"][str(h)] is not None])
                                       for h in horizons},
            "n_graded_at_own_horizon": len(graded_own),
            "own_horizon_brier": (float(np.mean([r["own_horizon_brier"] for r in graded_own]))
                                  if graded_own else None),
            "own_horizon_hit": (float(np.mean([r["own_horizon_call_right"] for r in graded_own]))
                                if graded_own else None),
            "mean_probability": float(np.mean([float(r["probability"]) for r in rows
                                               if r.get("probability") is not None]))
            if any(r.get("probability") is not None for r in rows) else None,
        }

    return {
        "headline": gap(graded, horizons),
        "n_decision_rows": len(graded),
        "n_decision_days": len({g["date"] for g in graded}),
        "status_counts": status,
        "benchmarks_by_day": dict(sorted(bench_day.items())),
        "by_direction": table_dir,
        "by_day": table_day,
        "refused_but_rose": _list("REFUSED", 1),
        "bought_but_fell": _list("BUY", -1),
        "bought_and_rose": _list("BUY", 1),
        "probed_but_rose": _list("PROBE", 1)[:25],
        "n_predictions": len(pred_rows),
        "predictions_by_specialist": spec_table,
        "predictions": pred_rows,
    }


# ─────────────────────────────── bars ───────────────────────────────────────

def _us_session_complete_through() -> date:
    """Last US date whose regular session has closed (ET 16:30 cut-off)."""
    now_utc = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        et = now_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:                                              # noqa: BLE001
        et = now_utc - timedelta(hours=4)
    d = et.date()
    if (et.hour, et.minute) < (16, 30):
        d = d - timedelta(days=1)
    return d


def load_bars(tickers: list[str], *, fetch: bool, start: str) -> tuple[pd.DataFrame, dict]:
    from backend.services import xs_ranker as XR
    want = sorted(set(tickers) | {MARKET})
    paths = XR.survivorship_free_paths() + [
        XR.BARS_PATH, XR.BARS_PATH.with_name("bars_forecast_only.parquet")]
    frames, src = [], {}
    for p in paths:
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=["symbol", "date", "open", "close"],
                             filters=[("symbol", "in", want)])
        df = df[pd.to_datetime(df["date"]) >= pd.Timestamp(start)]
        src[p.name] = {"rows": int(len(df)),
                       "last": str(pd.to_datetime(df["date"]).max().date()) if len(df) else None}
        frames.append(df)
    if fetch:
        try:
            from scripts import pull_forecast_bars as PFB
            end = _us_session_complete_through()
            f = PFB.fetch(want, start=start, end=str(end))
            if not f.empty:
                f = f[pd.to_datetime(f["date"]) <= pd.Timestamp(end)]
                frames.append(f[["symbol", "date", "open", "close"]])
            src["alpaca_fetch"] = {"rows": int(len(f)), "through": str(end),
                                   "last": str(pd.to_datetime(f["date"]).max().date()) if len(f) else None}
        except SystemExit as exc:                  # data_credential REFUSES this way
            src["alpaca_fetch"] = {"status": "REFUSED", "why": str(exc)[:300]}
        except Exception as exc:                                   # noqa: BLE001
            src["alpaca_fetch"] = {"status": "FAILED", "why": f"{type(exc).__name__}: {exc}"[:300]}
    bars = pd.concat(frames, ignore_index=True)
    bars["date"] = pd.to_datetime(bars["date"])
    # Local panels first: on a collision the panel the books are marked against wins.
    bars = bars.drop_duplicates(["symbol", "date"], keep="first")
    return bars, src


def load_universe(*, fetch: bool, start: str) -> tuple[UniverseMedian | None, dict]:
    """The funnel's own universe: `xs_ranker.BARS_PATH` (what `u_rank` reads),
    eligibility by `xs_ranker.mark_eligible`, plus -- with `fetch` -- the
    sessions after the panel's last date for every name eligible in its last
    month (Alpaca DATA endpoint, no orders, no LLM)."""
    from backend.services import xs_ranker as XR
    info: dict = {"panel": str(XR.BARS_PATH.name)}
    if not XR.BARS_PATH.exists():
        info["status"] = "NO_PANEL"
        return None, info
    bars = pd.read_parquet(XR.BARS_PATH, columns=["symbol", "date", "open", "close", "volume"])
    bars["date"] = pd.to_datetime(bars["date"])
    bars = bars[bars["date"] >= pd.Timestamp(UNIVERSE_HISTORY_START)]
    last = bars["date"].max()
    info.update({"panel_rows": int(len(bars)), "panel_symbols": int(bars["symbol"].nunique()),
                 "panel_last": str(last.date())})
    elig = eligibility(bars)
    recent = elig[(elig["date"] > last - pd.Timedelta(days=31)) & elig["eligible"]]
    names = sorted(set(recent["symbol"]))
    info["eligible_on_panel_last"] = int(elig[(elig["date"] == last) & elig["eligible"]].shape[0])
    if fetch and names:
        try:
            from scripts import pull_forecast_bars as PFB
            end = _us_session_complete_through()
            f = PFB.fetch(names, start=str((last + pd.Timedelta(days=1)).date()), end=str(end))
            if not f.empty:
                f["date"] = pd.to_datetime(f["date"])
                f = f[(f["date"] > last) & (f["date"] <= pd.Timestamp(end))]
                bars = pd.concat([bars, f[["symbol", "date", "open", "close", "volume"]]],
                                 ignore_index=True)
            info["fetch"] = {"names": len(names), "rows": int(len(f)), "through": str(end),
                             "last": str(f["date"].max().date()) if len(f) else None}
        except SystemExit as exc:
            info["fetch"] = {"status": "REFUSED", "why": str(exc)[:300]}
        except Exception as exc:                                   # noqa: BLE001
            info["fetch"] = {"status": "FAILED", "why": f"{type(exc).__name__}: {exc}"[:300]}
    bars = bars[bars["date"] >= pd.Timestamp(start)]
    elig = elig[elig["date"] >= pd.Timestamp(start) - pd.Timedelta(days=40)]
    return UniverseMedian(bars, elig), info


# ─────────────────────────────────── main ───────────────────────────────────

def _p(v) -> str:
    return "    n/a" if v is None else f"{v*100:+6.2f}%"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true",
                    help="add fresh daily bars from the Alpaca DATA endpoint (no orders, no LLM)")
    ap.add_argument("--since", default=PREDICTIONS_SINCE)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    skipped: dict = {}
    decisions = load_decisions(skipped=skipped)
    predictions = load_predictions(since=a.since)
    tickers = sorted({r["ticker"] for r in decisions} | {p["ticker"] for p in predictions})
    first = min([r["date"] for r in decisions] + [p["date"] for p in predictions] or ["2026-09-01"])
    start = str((pd.Timestamp(first) - pd.Timedelta(days=10)).date())
    bars, sources = load_bars(tickers, fetch=a.fetch, start=start)
    universe, uinfo = load_universe(fetch=a.fetch, start=start)
    prices = Prices(bars, universe=universe)
    res = autopsy(decisions, predictions, prices)

    print(f"decision rows {res['n_decision_rows']} over "
          f"{len({r['date'] for r in decisions})} day(s); predictions since {a.since}: "
          f"{res['n_predictions']}; last priced session {prices.last_session}")
    print(f"bar sources: {json.dumps(sources)}")
    print(f"not graded (not a single name): {json.dumps(skipped)}")
    print(f"universe benchmark ({UNIVERSE}): {json.dumps(uinfo)}")

    print("\nHEADLINE: PROBE - REFUSED, over the universe median (SPY beside it)")
    for h, x in res["headline"].items():
        t = x["day_matched_t"]
        print(f"  {h:>2}d  pooled vs XS median {_p(x['pooled_vs_universe_median'])}  "
              f"(vs SPY {_p(x['pooled_vs_spy'])})  n PROBE {x['n_rows_PROBE']} / REFUSED "
              f"{x['n_rows_REFUSED']} rows; day-matched {_p(x['day_matched_gap'])} over "
              f"{x['n_date_blocks']} date block(s)" + (f", t {t:+.2f}" if t is not None else ""))

    def _u(v):
        return "  n/a" if v is None else f"{round(v*100):>3}%"
    print("\nBY DIRECTION (n / mean vs SPY / mean vs XS median / share up vs XS median; "
          "then the benchmarks' own mean returns)")
    for d, t in res["by_direction"].items():
        print(f"  {d:<8} " + "  ".join(
            f"{h}d n={c['n']:<3} SPY {_p(c['mean_rel'])} XS {_p(c['mean_rel_univ'])} "
            f"up {_u(c['share_up_univ'])} [spy {_p(c['mean_spy'])} xs {_p(c['mean_univ'])}]"
            for h, c in t.items()))
    print("\nBENCHMARKS BY DAY (SPY return / XS median return / names in the median)")
    for day, hh in res["benchmarks_by_day"].items():
        print(f"  {day} " + "  ".join(
            f"{h}d {b['entry']}->{b['exit']} SPY {_p(b['spy'])} XS {_p(b['universe_median'])} "
            f"(n={b['universe_n']})" for h, b in hh.items()))
    print("\nBY DAY (mean vs SPY / mean vs XS median)")
    for day, dd in res["by_day"].items():
        for d, t in dd.items():
            print(f"  {day} {d:<8} " + "  ".join(
                f"{h}d n={c['n']:<3} SPY {_p(c['mean_rel'])} XS {_p(c['mean_rel_univ'])}"
                for h, c in t.items()))
    print(f"\nREFUSED BUT ROSE ({len(res['refused_but_rose'])}):")
    for r in res["refused_but_rose"][:15]:
        print(f"  {r['date']} {r['ticker']:<6} {r['horizon']}d SPY {_p(r['rel'])} "
              f"XS {_p(r['rel_univ'])}  {r['terminal_state']}")
    print(f"BOUGHT BUT FELL ({len(res['bought_but_fell'])}); bought and rose "
          f"({len(res['bought_and_rose'])}):")
    for r in res["bought_but_fell"][:15]:
        print(f"  {r['date']} {r['ticker']:<6} {r['horizon']}d SPY {_p(r['rel'])} "
              f"XS {_p(r['rel_univ'])}")
    print("\nFORECASTS BY SPECIALIST")
    for s, t in res["predictions_by_specialist"].items():
        print(f"  {s:<36} n={t['n']:<3} graded@own={t['n_graded_at_own_horizon']:<3} "
              f"hit {t['own_horizon_hit']} brier {t['own_horizon_brier']} " + "  ".join(
                  f"{h}d SPY {_p(c['mean_rel'])} XS {_p(t['by_horizon_vs_universe'][h]['mean_rel'])}"
                  f"(n={c['n']})" for h, c in t["by_horizon"].items()))

    receipt = {
        "receipt": "decision_autopsy", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "convention": ("entry at the OPEN of the first session after the decision date, mark at "
                       "the close h sessions later; rel = stock - SPY over the same window; "
                       "rel_univ = stock - the MEDIAN same-window return of the names "
                       "xs_ranker.mark_eligible admits on the decision date (the headline "
                       "benchmark); no cost charged (grades the call, not a book); PENDING is "
                       "not zero"),
        "benchmarks": {"spy": MARKET, "universe": UNIVERSE, "universe_info": uinfo,
                       "min_universe_names": MIN_UNIVERSE_NAMES},
        "horizons_sessions": list(HORIZONS),
        "last_priced_session": prices.last_session,
        "bar_sources": sources,
        "decision_files": sorted(p.name for p in DECISIONS_DIR.glob("20*.json")),
        "predictions_since": a.since,
        "rows_not_graded_not_a_single_name": skipped,
        **res,
    }
    out = Path(a.out) if a.out else DECISIONS_DIR / f"autopsy_{date.today()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
