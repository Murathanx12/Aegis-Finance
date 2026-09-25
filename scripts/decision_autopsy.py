"""What happened to the names we bought, probed and refused? The decision autopsy.

    python -m scripts.decision_autopsy            # local bars only
    python -m scripts.decision_autopsy --fetch    # + fresh daily bars (Alpaca DATA endpoint)

For every row of `<OPTIMUS_LEDGER_DIR>/decisions/YYYY-MM-DD.json` carrying a
ticker and a direction (BUY / PROBE / REFUSED / WATCH / SELL), and every
`predictions.jsonl` row made since 2026-09-11, the realised 1/5/21-session
return RELATIVE TO SPY, entered at the OPEN of the first session after the
decision date and marked at the close `h` sessions later (the same convention
as `llm_portfolio.grade`). No cost is charged: this grades the CALL, not a
book.

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
    for f in sorted(folder.glob("20[0-9][0-9]-[01][0-9]-[0-3][0-9].json")):
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
            key = (day, t, direction)
            if key in seen:
                continue
            seen.add(key)
            out.append({"date": day, "ticker": t, "direction": direction,
                        "terminal_state": r.get("terminal_state"),
                        "authority": r.get("authority"),
                        "refusal_class": r.get("refusal_class"),
                        "signal": r.get("signal"),
                        "decision_id": r.get("decision_id")})
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

class Prices:
    """Per-symbol (dates, open, close) arrays, built once."""

    def __init__(self, bars: pd.DataFrame):
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
            out[h] = {"status": "OK", "ret": r, "spy": m, "rel": r - m,
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
    for g in graded:
        for h in horizons:
            x = g["rel"][h]
            status.setdefault(g["direction"], {}).setdefault(str(h), {}).setdefault(x["status"], 0)
            status[g["direction"]][str(h)][x["status"]] += 1
            if x["status"] != "OK":
                continue
            by_dir.setdefault(g["direction"], {}).setdefault(h, []).append(x["rel"])
            by_day.setdefault(g["date"], {}).setdefault(g["direction"], {}).setdefault(h, []).append(x["rel"])

    table_dir = {d: {str(h): _summ(by_dir.get(d, {}).get(h, [])) for h in horizons}
                 for d in sorted({g["direction"] for g in graded})}
    table_day = {day: {d: {str(h): _summ(v.get(h, [])) for h in horizons} for d, v in dd.items()}
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
                         "rel": rel, "terminal_state": g.get("terminal_state"),
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
        "n_decision_rows": len(graded),
        "status_counts": status,
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
    prices = Prices(bars)
    res = autopsy(decisions, predictions, prices)

    print(f"decision rows {res['n_decision_rows']} over "
          f"{len({r['date'] for r in decisions})} day(s); predictions since {a.since}: "
          f"{res['n_predictions']}; last priced session {prices.last_session}")
    print(f"bar sources: {json.dumps(sources)}")
    print(f"not graded (not a single name): {json.dumps(skipped)}")
    print("\nBY DIRECTION (relative to SPY; n / mean / share up)")
    for d, t in res["by_direction"].items():
        print(f"  {d:<8} " + "  ".join(
            f"{h}d n={c['n']:<3} {_p(c['mean_rel'])} up {c['share_up'] if c['share_up'] is None else round(c['share_up']*100)}%"
            for h, c in t.items()))
    print("\nBY DAY")
    for day, dd in res["by_day"].items():
        for d, t in dd.items():
            print(f"  {day} {d:<8} " + "  ".join(
                f"{h}d n={c['n']:<3} {_p(c['mean_rel'])}" for h, c in t.items()))
    print(f"\nREFUSED BUT ROSE ({len(res['refused_but_rose'])}):")
    for r in res["refused_but_rose"][:15]:
        print(f"  {r['date']} {r['ticker']:<6} {r['horizon']}d {_p(r['rel'])}  {r['terminal_state']}")
    print(f"BOUGHT BUT FELL ({len(res['bought_but_fell'])}); bought and rose "
          f"({len(res['bought_and_rose'])}):")
    for r in res["bought_but_fell"][:15]:
        print(f"  {r['date']} {r['ticker']:<6} {r['horizon']}d {_p(r['rel'])}")
    print("\nFORECASTS BY SPECIALIST")
    for s, t in res["predictions_by_specialist"].items():
        print(f"  {s:<36} n={t['n']:<3} graded@own={t['n_graded_at_own_horizon']:<3} "
              f"hit {t['own_horizon_hit']} brier {t['own_horizon_brier']} " + "  ".join(
                  f"{h}d {_p(c['mean_rel'])}(n={c['n']})" for h, c in t["by_horizon"].items()))

    receipt = {
        "receipt": "decision_autopsy", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "convention": ("entry at the OPEN of the first session after the decision date, mark at "
                       "the close h sessions later; relative = stock - SPY over the same window; "
                       "no cost charged (grades the call, not a book); PENDING is not zero"),
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
