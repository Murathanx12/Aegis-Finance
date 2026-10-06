"""book_dna -- "N ahead of SPY" is never printed again without its collapse factor.

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM, no order, no broker call).
Chunk C3 of `docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md`, from the
research note `docs/research_notes/2026-10-06/winner_loser_dna_2026-10-06.md`.

THE FINDING THIS MODULE MAKES MECHANICAL
========================================
On 2026-10-06 the paper-accounts receipt said "148 of 307 ahead of SPY". 105 of
the 148 were control TWINS (re-pricings of 64 books); the non-twin winners
shared a handful of baskets (one semiconductor/memory cluster held MU in 54% of
winner books); four website lanes were one risk dial; mirror and conviction were
one 12-name book with two different caps; PC-PAPER's edge was one position.
Every one of those facts was true of the receipt and invisible in its headline.

So this module reads the SAME ROI receipt (`scripts/paper_accounts_roi.py` calls
it before writing) plus each book's holdings and return series, and writes
`paper_accounts/book_dna_<run_id>.json` beside it:

* per book: family, twin_of, sessions graded, return, SPY own-window leg, excess,
  an evidence label (OBSERVED(n) / EARLY_EVIDENCE / REPLICATED -- never higher
  from this module), the TAIL check (top-1 / top-2 holdings' share of the excess),
  top sector weight and HHI, beta vs SPY where a long enough series exists, cash
  fraction, `one_name_dependence`;
* clusters of the non-twin books ahead: holdings Jaccard (threshold in config,
  with the count at every sensitivity threshold printed) plus return correlation
  where series exist; members, shared basket, cluster excess;
* lanes: the daily-return correlation matrix, the risk-dial families it implies,
  and an identity statement for lanes that hold the same names -- all DERIVED;
* losers: the bottom N with an `error_type` chosen by a declared rule order.

The summary goes INTO the ROI receipt's `aggregate` (`n_ahead_raw`,
`n_ahead_non_twin`, `n_independent_clusters_ahead`, `collapse_factor`,
`largest_cluster_share`, `largest_cluster_basket`, `collapse_line`), and every
writer that prints the count prints `collapse_line` with it.

WHAT IT DOES NOT DO
===================
It labels nothing above REPLICATED: VALIDATED_EDGE needs a validator run on data
the idea never saw, which is not this module's job (roadmap section 7). A field
it cannot compute says NOT_COMPUTABLE with a reason -- never 0, never absent.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _config

SCHEMA = "book_dna/1"
NOT_COMPUTABLE = "NOT_COMPUTABLE"
#: The ladder from roadmap section 7. This module may award only the first three.
LABEL_LADDER = ("OBSERVED", "EARLY_EVIDENCE", "REPLICATED", "VALIDATED_EDGE")
LABEL_CEILING = "REPLICATED"
ERROR_TYPES = ("control_artifact", "unmanaged", "sizing_concentration",
               "timing_exit", "selection", "not_determinable")
CASH_TICKERS = {"CASH", "USD", "$CASH"}

_OPT = Path(_config.OPTIMUS_LEDGER_DIR)
PA_DIR = _OPT / "paper_accounts"
LLM_DIR = _OPT / "llm_portfolio"
PC_NAV = _OPT / "pc_book" / "nav.jsonl"
UNIVERSE_DIR = _OPT / "potential_universe"
PROD = "https://aegis-finance-production.up.railway.app"


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def params() -> dict:
    """Every threshold, read from config at call time and printed on the receipt."""
    return {
        "jaccard_threshold": float(_cfg("BOOK_DNA_JACCARD_THRESHOLD", 0.30)),
        "jaccard_sensitivity": [float(x) for x in _cfg("BOOK_DNA_JACCARD_SENSITIVITY", (0.15, 0.30, 0.50))],
        "corr_threshold": float(_cfg("BOOK_DNA_CORR_THRESHOLD", 0.80)),
        "min_corr_obs": int(_cfg("BOOK_DNA_MIN_CORR_OBS", 15)),
        "min_beta_obs": int(_cfg("BOOK_DNA_MIN_BETA_OBS", 20)),
        "early_min_sessions": int(_cfg("BOOK_DNA_EARLY_MIN_SESSIONS", 21)),
        "fair_twin_kinds": list(_cfg("BOOK_DNA_FAIR_TWIN_KINDS",
                                     ("matched_twin21", "matched_random", "random_same_band"))),
        "one_name_share": float(_cfg("BOOK_DNA_ONE_NAME_SHARE", 0.50)),
        "n_losers": int(_cfg("BOOK_DNA_N_LOSERS", 10)),
        "unmanaged_sessions": int(_cfg("BOOK_DNA_UNMANAGED_SESSIONS", 5)),
        "loser_sizing_share": float(_cfg("BOOK_DNA_LOSER_SIZING_SHARE", 0.40)),
        "timing_share": float(_cfg("BOOK_DNA_TIMING_SHARE", 0.70)),
        "loser_weight_fallback": float(_cfg("BOOK_DNA_LOSER_WEIGHT_FALLBACK", 0.20)),
        "lane_family_corr": float(_cfg("BOOK_DNA_LANE_FAMILY_CORR", 0.85)),
        "lane_identity_jaccard": float(_cfg("BOOK_DNA_LANE_IDENTITY_JACCARD", 0.90)),
        "basket_top": int(_cfg("BOOK_DNA_BASKET_TOP", 5)),
    }


# ───────────────────────────── prices ───────────────────────────────────────

class Prices:
    """Open/close lookups by symbol and ISO date, from a long bars frame."""

    def __init__(self, bars: Optional[pd.DataFrame]):
        self.ok = bars is not None and len(bars) > 0
        if not self.ok:
            self.close = pd.DataFrame()
            self.open = pd.DataFrame()
            return
        b = bars[["symbol", "date", "open", "close"]].copy()
        b["date"] = pd.to_datetime(b["date"]).dt.strftime("%Y-%m-%d")
        b = b.drop_duplicates(subset=["symbol", "date"], keep="first")
        self.close = b.pivot(index="date", columns="symbol", values="close").sort_index()
        self.open = b.pivot(index="date", columns="symbol", values="open").sort_index()

    def has(self, sym: str) -> bool:
        return self.ok and sym in self.close.columns

    def dates(self, sym: str = "SPY") -> list[str]:
        if not self.has(sym):
            return []
        return list(self.close[sym].dropna().index)

    def close_on_or_before(self, sym: str, d: str) -> float:
        if not self.has(sym) or not d:
            return float("nan")
        s = self.close[sym].dropna()
        s = s[s.index <= str(d)[:10]]
        return float(s.iloc[-1]) if len(s) else float("nan")

    def open_on(self, sym: str, d: str) -> float:
        if not self.has(sym) or not d:
            return float("nan")
        v = self.open[sym].get(str(d)[:10], float("nan"))
        return float(v) if v == v else float("nan")

    def spy_period_returns(self, dates: list[str]) -> list[float]:
        c = [self.close_on_or_before("SPY", d) for d in dates]
        return [c[i] / c[i - 1] - 1.0 if c[i - 1] and c[i - 1] == c[i - 1] and c[i] == c[i] else float("nan")
                for i in range(1, len(c))]


def load_prices(symbols: Iterable[str], bars: Optional[pd.DataFrame] = None) -> tuple[Prices, str]:
    """The bars panel (`xs_ranker.load_bars`) plus the llm_portfolio global panel
    for foreign tickers, restricted to `symbols` + SPY."""
    want = set(symbols) | {"SPY"}
    srcs = []
    frames = []
    if bars is None:
        try:
            from backend.services import xs_ranker
            b = xs_ranker.load_bars()
            frames.append(b[b["symbol"].isin(want)])
            srcs.append("xs_ranker.load_bars()")
        except Exception as e:                      # a missing panel is a named gap
            srcs.append(f"xs_ranker.load_bars() FAILED: {type(e).__name__}: {e}"[:200])
        g = LLM_DIR / "global_bars.parquet"
        if g.exists():
            try:
                gb = pd.read_parquet(g, columns=["symbol", "date", "open", "close"])
                frames.append(gb[gb["symbol"].isin(want)])
                srcs.append("llm_portfolio/global_bars.parquet")
            except Exception as e:
                srcs.append(f"global_bars FAILED: {type(e).__name__}")
    else:
        frames.append(bars[bars["symbol"].isin(want)])
        srcs.append("injected")
    df = pd.concat(frames, ignore_index=True) if frames else None
    return Prices(df), " + ".join(srcs)


# ───────────────────────────── input loading (disk) ─────────────────────────

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _session_date_of_stamp(t: str) -> Optional[str]:
    """US session a broker equity stamp marks: after 16:00 ET -> that day; before
    09:30 ET -> the previous weekday; intraday -> None (not a close)."""
    try:
        ts = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None
    try:
        from zoneinfo import ZoneInfo
        et = ts.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        et = ts.astimezone(timezone(timedelta(hours=-4)))
    hm = et.hour * 60 + et.minute
    if hm >= 16 * 60:
        return et.date().isoformat()
    if hm < 9 * 60 + 30:
        d = et.date() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()
    return None


def load_inputs(receipt: dict, *, http_get: Optional[Callable] = None,
                fetch_lanes: bool = True) -> dict:
    """Read every holdings / series source this module uses. Each source that
    fails is recorded in `inputs["gaps"]`, never raised."""
    gaps: dict = {}
    inp: dict = {"gaps": gaps}
    recs = [r for r in _read_jsonl(LLM_DIR / "books.jsonl") if r.get("schema") != "llm_portfolio/void"]
    inp["books"] = recs
    lbs = []
    for f in sorted(LLM_DIR.glob("leaderboard_*.json")):
        try:
            lbs.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            gaps[f.name] = f"unreadable: {type(e).__name__}"
    inp["leaderboards"] = lbs
    # alpaca fleet: newest fleet_daily read (positions with market value + plpc)
    fleet_pos: dict = {}
    fd = sorted((PA_DIR / "fleet_daily").glob("fleet_*.json"))
    if fd:
        try:
            d = json.loads(fd[-1].read_text(encoding="utf-8"))
            for a in d.get("accounts") or []:
                pos = []
                for p in a.get("positions") or []:
                    mv = float(p.get("market_value") or 0.0)
                    try:
                        plpc = float(p.get("unrealized_plpc"))
                        upl = mv * plpc / (1.0 + plpc) if plpc > -1 else None
                    except (TypeError, ValueError):
                        upl = None
                    pos.append({"symbol": p.get("symbol"), "market_value": mv, "unrealized_pl": upl})
                fleet_pos[a.get("role")] = {"positions": pos, "equity": a.get("equity"),
                                            "cash": a.get("cash"), "source": f"fleet_daily/{fd[-1].name}"}
        except (OSError, ValueError) as e:
            gaps["fleet_daily"] = f"unreadable: {type(e).__name__}"
    else:
        gaps["fleet_daily"] = "no fleet_daily/fleet_*.json"
    inp["fleet_positions"] = fleet_pos
    st: dict = {}
    for f in sorted((PA_DIR / "fleet_manager" / "state").glob("hack*.json")):
        try:
            st[f.stem] = json.loads(f.read_text(encoding="utf-8")).get("t")
        except (OSError, ValueError):
            gaps[f"fleet_state/{f.name}"] = "unreadable"
    inp["fleet_manager_last_run"] = st
    grades: dict = {}
    for g in _read_jsonl(PA_DIR / "fleet_manager" / "grades.jsonl"):
        if g.get("account_return") is None or g.get("spy_return") is None:
            continue
        grades.setdefault(g.get("role"), {})[str(g.get("session"))] = (
            float(g["account_return"]), float(g["spy_return"]))
    inp["fleet_grades"] = {r: sorted((d, a, s) for d, (a, s) in v.items()) for r, v in grades.items()}
    # PC-PAPER
    try:
        inp["pc_state"] = json.loads((PA_DIR / "pc_snapshot" / "state_latest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        inp["pc_state"] = None
        gaps["pc_snapshot"] = f"unreadable: {type(e).__name__}"
    pcn: dict = {}
    last_t = None
    for r in _read_jsonl(PC_NAV):
        last_t = r.get("t") or last_t
        d = _session_date_of_stamp(r.get("t") or "")
        if d and r.get("equity") is not None:
            pcn[d] = float(r["equity"])
    inp["pc_nav"] = sorted(pcn.items())
    inp["pc_manager_last_run"] = last_t
    # night books
    try:
        from backend.services import paper_books as PB
        inp["night_nav"] = PB.nav_series()
    except Exception as e:
        inp["night_nav"] = {}
        gaps["paper_books.nav_series"] = f"{type(e).__name__}: {e}"[:200]
    # website lane positions (read-only GET of the live deploy's positions route)
    lanes = [r["account"] for r in receipt.get("rows") or [] if r.get("family") == "website_lane"]
    lp: dict = {}
    if fetch_lanes and lanes:
        get = http_get
        if get is None:
            try:
                import requests
                get = lambda u: requests.get(u, timeout=20)      # noqa: E731
            except ImportError:
                get = None
        for lane in lanes:
            if get is None:
                gaps[f"lane_positions/{lane}"] = "no http client"
                continue
            try:
                resp = get(f"{PROD}/api/pi/lane/{lane}/positions")
                if getattr(resp, "status_code", 200) != 200:
                    gaps[f"lane_positions/{lane}"] = f"HTTP {resp.status_code}"
                    continue
                d = resp.json()
                lp[lane] = {"positions": [(p["ticker"], float(p["shares"])) for p in d.get("positions") or []],
                            "source": f"GET /api/pi/lane/{lane}/positions"}
            except Exception as e:
                gaps[f"lane_positions/{lane}"] = f"{type(e).__name__}"[:120]
    elif lanes:
        gaps["lane_positions"] = "not fetched (fetch_lanes=False)"
    inp["lane_positions"] = lp
    inp["lane_caps"] = declared_lane_caps(lanes)
    inp["sector_map"], inp["sector_source"] = load_sector_map()
    return inp


#: The registered lane configs config.py loads (one YAML each).
LANE_CONFIG_ATTRS = ("paper_portfolios", "book_lanes", "conservative_atr_lanes",
                     "smallmid_quality_lanes", "tsmom_xa_lanes")


def declared_lane_caps(lanes: Iterable[str]) -> dict:
    """{lane: {"max_single_name": float|None, "source": attr}} from the lane
    configs config.py loads. None = the lane's registered config declares NO cap;
    a lane no loaded config describes is absent (UNKNOWN), never assumed uncapped."""
    out: dict = {}
    for attr in LANE_CONFIG_ATTRS:
        d = getattr(_config, attr, None) or {}
        if not isinstance(d, dict):
            continue
        pools = [d] + [v for v in d.values() if isinstance(v, dict) and any(
            isinstance(x, dict) for x in v.values())]
        for lane in lanes:
            if lane in out:
                continue
            for pool in pools:
                if isinstance(pool.get(lane), dict):
                    out[lane] = {"max_single_name": pool[lane].get("max_single_name"),
                                 "source": f"config.{attr}"}
                    break
    return out


def load_sector_map() -> tuple[dict, str]:
    files = sorted(UNIVERSE_DIR.glob("*.jsonl"))
    if not files:
        return {}, "none (no potential_universe/*.jsonl)"
    m = {}
    for r in _read_jsonl(files[-1]):
        s = (r.get("identity") or {}).get("sector")
        if s and r.get("symbol"):
            m[r["symbol"]] = s
    return m, f"potential_universe/{files[-1].name} identity.sector ({len(m)} symbols)"


# ───────────────────────────── per-book pieces (pure) ───────────────────────

def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def beta_of(series: Optional[list], min_obs: int) -> Any:
    if not series:
        return {"value": NOT_COMPUTABLE, "why": "no period-return series", "n_obs": 0}
    pts = [(b, s) for _, b, s in series if _num(b) is not None and _num(s) is not None]
    if len(pts) < min_obs:
        return {"value": NOT_COMPUTABLE, "why": f"{len(pts)} period returns < {min_obs}", "n_obs": len(pts)}
    x = np.array([s for _, s in pts])
    y = np.array([b for b, _ in pts])
    vx = float(np.var(x))
    if vx <= 0:
        return {"value": NOT_COMPUTABLE, "why": "SPY returns have zero variance", "n_obs": len(pts)}
    beta = float(np.cov(x, y, ddof=0)[0, 1] / vx)
    corr = float(np.corrcoef(x, y)[0, 1]) if np.std(y) > 0 else None
    return {"value": round(beta, 3), "corr_vs_spy": None if corr is None else round(corr, 3),
            "n_obs": len(pts)}


def subwindows(series: Optional[list], sessions: Optional[int], min_cover: float = 0.8) -> dict:
    """Excess (book compounded - SPY compounded) in three contiguous thirds of the
    period-return series. Requires the series to cover >= `min_cover` of the
    sessions graded -- a series that starts late cannot speak for the window."""
    if not series or len(series) < 3:
        return {"status": NOT_COMPUTABLE, "why": "fewer than 3 period returns"}
    if sessions and len(series) < min_cover * sessions:
        return {"status": NOT_COMPUTABLE,
                "why": f"series covers {len(series)} of {sessions} sessions (< {min_cover:.0%})"}
    chunks = np.array_split(np.arange(len(series)), 3)
    out = []
    for idx in chunks:
        b = float(np.prod([1 + series[i][1] for i in idx]) - 1)
        s = float(np.prod([1 + series[i][2] for i in idx]) - 1)
        out.append({"from": series[idx[0]][0], "to": series[idx[-1]][0],
                    "excess_pp": round(100 * (b - s), 3)})
    return {"status": "OK", "windows": out, "n_positive": sum(1 for w in out if w["excess_pp"] > 0)}


def tail_from_contributions(contrib: dict, *, basis: str, note: str = "",
                            min_abs: float = 1e-4) -> dict:
    """Top-1 / top-2 holdings' share of the signed total. The top names are the
    largest contributors IN THE DIRECTION of the total (gains for a winner,
    losses for a loser), so a share above 100% means everything else netted
    against it."""
    vals = {k: v for k, v in contrib.items() if _num(v) is not None}
    tot = sum(vals.values())
    if not vals or abs(tot) < min_abs:
        return {"status": NOT_COMPUTABLE, "basis": basis,
                "why": "no priced contribution" if not vals else "total ~ 0: a share of nothing"}
    sgn = 1.0 if tot > 0 else -1.0
    ranked = sorted(vals.items(), key=lambda kv: -sgn * kv[1])
    t1 = ranked[0]
    t2 = ranked[1] if len(ranked) > 1 else (None, 0.0)
    out = {"status": "OK", "basis": basis, "total": round(tot, 6),
           "top1": {"ticker": t1[0], "share": round(t1[1] / tot, 3)},
           "top2": {"tickers": [t1[0]] + ([t2[0]] if t2[0] else []),
                    "share": round((t1[1] + t2[1]) / tot, 3)}}
    if note:
        out["note"] = note
    return out


def concentration(weights: dict, sector_map: dict) -> dict:
    """Top-1 weight, HHI and top sector of the INVESTED part. A holding with no
    price (weight None/NaN) makes the numbers partial, and the row says so."""
    unpriced = sorted(k for k, v in (weights or {}).items()
                      if k not in CASH_TICKERS and _num(v) is None)
    w = {k: float(v) for k, v in (weights or {}).items()
         if k not in CASH_TICKERS and _num(v) is not None and float(v) > 0}
    tot = sum(w.values())
    if not w or tot <= 0:
        return {"status": NOT_COMPUTABLE, "why": "no holdings with a weight"}
    if unpriced:
        return {"status": "PARTIAL", "unpriced": unpriced,
                "why": f"{len(unpriced)} holding(s) unpriced in the bars panel; weights of the "
                       f"priced names only would overstate concentration",
                "n_names": len(w) + len(unpriced),
                "top1_weight_of_equity": _top1(w)}
    n = {k: v / tot for k, v in w.items()}
    top = max(n.items(), key=lambda kv: kv[1])
    sec: dict = {}
    covered = 0.0
    for k, v in n.items():
        s = sector_map.get(k)
        if s:
            sec[s] = sec.get(s, 0.0) + v
            covered += v
    out = {"status": "OK", "n_names": len(n), "top1_weight_of_invested": {"ticker": top[0], "weight": round(top[1], 3)},
           "hhi_names": round(sum(v * v for v in n.values()), 4),
           "sector_coverage": round(covered, 3)}
    if covered >= 0.5:
        ts = max(sec.items(), key=lambda kv: kv[1])
        out["top_sector"] = {"sector": ts[0], "weight_of_covered": round(ts[1] / covered, 3)}
        out["hhi_sectors"] = round(sum((v / covered) ** 2 for v in sec.values()), 4)
    else:
        out["top_sector"] = {"status": NOT_COMPUTABLE, "why": f"sector known for {covered:.0%} of the weight"}
    return out


def _top1(w: dict) -> dict:
    t = max(w.items(), key=lambda kv: kv[1])
    return {"ticker": t[0], "weight": round(t[1], 3)}


def evidence_label(*, sessions: Optional[int], excess_pp: Optional[float], sub: dict,
                   fair_twin_excess_pp: Optional[float], replicated_by: Optional[str],
                   p: dict) -> dict:
    """OBSERVED(n) -> EARLY_EVIDENCE -> REPLICATED. Never higher (LABEL_CEILING)."""
    n = sessions if sessions is not None else 0
    lab = f"OBSERVED({n})"
    why = "default: a number over n sessions"
    early = (n >= p["early_min_sessions"] and (excess_pp or 0) > 0
             and sub.get("status") == "OK" and sub.get("n_positive", 0) >= 2)
    if early:
        lab, why = "EARLY_EVIDENCE", (f">= {p['early_min_sessions']} sessions, excess > 0, "
                                      f"{sub['n_positive']} of 3 sub-windows positive")
        if (fair_twin_excess_pp is not None and fair_twin_excess_pp > 0) or replicated_by:
            lab = "REPLICATED"
            why += ("; " + (f"frozen replication {replicated_by} also qualifies" if replicated_by
                            else f"excess over the fair twin {fair_twin_excess_pp:+.2f} pp"))
    elif n < p["early_min_sessions"]:
        why = f"{n} sessions < {p['early_min_sessions']}"
    elif (excess_pp or 0) <= 0:
        why = "excess <= 0"
    else:
        why = f"sub-windows: {sub.get('why') or str(sub.get('n_positive')) + ' of 3 positive'}"
    assert LABEL_LADDER.index(lab.split("(")[0]) <= LABEL_LADDER.index(LABEL_CEILING)
    return {"label": lab, "why": why}


# ───────────────────────────── holdings / series per family ─────────────────

def _llm_index(inputs: dict) -> tuple[dict, dict, dict]:
    books = {b["book_id"]: b for b in inputs.get("books") or [] if b.get("book_id")}
    # newest grade per book, and the period series from every leaderboard
    newest: dict = {}
    hist: dict = {}
    for lb in inputs.get("leaderboards") or []:
        bt = lb.get("bars_through")
        for g in lb.get("books") or []:
            bid = g.get("book_id")
            if not bid:
                continue
            newest[bid] = g
            if bt and g.get("net_to_date") is not None and g.get("benchmark_to_date") is not None \
                    and g.get("benchmark") == "SPY":
                hist.setdefault(bid, {})[bt] = (float(g["net_to_date"]), float(g["benchmark_to_date"]))
    series = {}
    for bid, pts in hist.items():
        cum = sorted(pts.items())
        s, pb, ps = [], 0.0, 0.0
        for d, (cb, cs) in cum:
            s.append((d, (1 + cb) / (1 + pb) - 1, (1 + cs) / (1 + ps) - 1))
            pb, ps = cb, cs
        series[bid] = s
    return books, newest, series


def _series_from_nav(nav: list, px: Prices) -> list:
    """[(date, nav)] -> [(date, r_book, r_spy)] using SPY closes on the same dates."""
    nav = [(str(d)[:10], float(v)) for d, v in nav if _num(v) is not None]
    if len(nav) < 2:
        return []
    dates = [d for d, _ in nav]
    rs = px.spy_period_returns(dates)
    out = []
    for i in range(1, len(nav)):
        if nav[i - 1][1] > 0 and _num(rs[i - 1]) is not None:
            out.append((dates[i], nav[i][1] / nav[i - 1][1] - 1, rs[i - 1]))
    return out


def _lane_series(receipt: dict, lane: str) -> list:
    ls = receipt.get("lane_nav_series") or {}
    pts = (ls.get("lanes") or {}).get(lane) or []
    spy = dict((d, v) for d, v in ls.get("spy_rebased_100k_at_2026_06_08") or [])
    pts = [(d, v) for d, v in pts if d in spy]
    out = []
    for i in range(1, len(pts)):
        d0, v0 = pts[i - 1]
        d1, v1 = pts[i]
        if v0 and spy[d0]:
            out.append((d1, v1 / v0 - 1, spy[d1] / spy[d0] - 1))
    return out


def _sessions(px: Prices, inception: Optional[str], last_mark: Optional[str], base: str) -> Optional[int]:
    if not inception or not last_mark:
        return None
    ds = px.dates("SPY")
    if not ds:
        return None
    inc, lm = str(inception)[:10], str(last_mark)[:10]
    if base in ("prior_close", "grade_entry_open"):
        return sum(1 for d in ds if inc <= d <= lm)
    return sum(1 for d in ds if inc < d <= lm)


def _sessions_since(px: Prices, stamp: Optional[str], today: date) -> Optional[int]:
    if not stamp:
        return None
    d = str(stamp)[:10]
    ds = px.dates("SPY")
    if not ds:
        return None
    return sum(1 for x in ds if d < x <= today.isoformat())


def _twin_parent_night(row: dict, rows: list) -> Optional[str]:
    ga = str(row.get("graded_against") or "").replace("—", "-").replace("–", "-")
    if not ga:
        return None
    for r in rows:
        if r.get("family") == "night_books" and str(r["account"]).startswith(ga.strip()[:40]):
            return r["account"]
    return ga


def book_rows(receipt: dict, inputs: dict, px: Prices, p: dict, today: date) -> list[dict]:
    rows = receipt.get("rows") or []
    books, newest, llm_series = _llm_index(inputs)
    smap = inputs.get("sector_map") or {}
    names = {b: r.get("name") for b, r in books.items()}
    rule_of = {b: str(r.get("model"))[5:] for b, r in books.items()
               if str(r.get("model") or "").startswith("rule:")}
    out = []
    for r in rows:
        if r.get("roi_pct") is None or r.get("equity") is None:
            continue
        fam = str(r.get("family"))
        acct = r["account"]
        excess = _num(r.get("vs_spy_pp"))
        spy_leg = _num(r.get("spy_same_window_pct"))
        e = {"account": acct, "family": fam, "status": r.get("status"),
             "return_pct": r.get("roi_pct"), "spy_leg_pct": spy_leg, "excess_pp": excess,
             "inception": r.get("inception"), "last_mark": r.get("last_mark"),
             "twin_of": None, "book_id": r.get("book_id")}
        weights: dict = {}
        holdings_source = None
        tail: dict = {"status": NOT_COMPUTABLE, "why": "no holdings source for this family"}
        series: list = []
        cash = {"value": NOT_COMPUTABLE, "why": "no cash source"}
        sessions = _sessions(px, r.get("inception"), r.get("last_mark"), str(r.get("spy_base")))
        manager_last = None
        fair_twin = None
        if fam.startswith("llm_portfolio"):
            b = books.get(r.get("book_id")) or {}
            g = newest.get(r.get("book_id")) or {}
            if b.get("kind") == "twin":
                e["twin_of"] = names.get(b.get("parent_book_id"), b.get("parent_book_id"))
                e["twin_kind"] = b.get("twin")
            sessions = g.get("sessions", sessions)
            weights = {str(x["ticker"]): float(x.get("weight") or 0.0) for x in b.get("positions") or []
                       if x.get("ticker")}
            holdings_source = "llm_portfolio/books.jsonl (frozen entry weights)"
            cw = _num(b.get("cash_weight"))
            cash = {"value": round(cw, 4) if cw is not None else 0.0, "basis": "frozen cash_weight"}
            series = llm_series.get(r.get("book_id")) or []
            for k in p["fair_twin_kinds"]:
                v = _num(g.get(f"vs_{k}"))
                if v is not None:
                    fair_twin = {"kind": k, "excess_over_twin_pp": round(100 * v, 3)}
                    break
            if spy_leg is not None and weights:
                rspy = spy_leg / 100.0
                contrib, unpriced = {}, 0.0
                for t, w in weights.items():
                    if t in CASH_TICKERS:
                        continue
                    o = px.open_on(t, r.get("inception"))
                    c = px.close_on_or_before(t, r.get("last_mark"))
                    if not (o > 0 and c == c):
                        unpriced += w
                        continue
                    contrib[t] = w * ((c / o - 1) - rspy)
                if (cw or 0) > 0:
                    contrib["CASH"] = -(cw or 0) * rspy
                inv = sum(w for t, w in weights.items() if t not in CASH_TICKERS)
                if inv > 0 and unpriced / inv > 0.2:
                    tail = {"status": NOT_COMPUTABLE, "basis": "active_contribution",
                            "why": f"{unpriced / inv:.0%} of the weight has no entry open / exit close"}
                else:
                    tail = tail_from_contributions(
                        contrib, basis="active_contribution",
                        note="w_i x (r_i - r_SPY), entry open to last-mark close, before costs")
                    if tail.get("status") == "OK":
                        tail["reconstructed_excess_pp"] = round(100 * tail["total"], 3)
                        tail["unpriced_weight"] = round(unpriced, 4)
        elif fam == "pc_paper":
            st = inputs.get("pc_state") or {}
            eq = _num(st.get("equity")) or _num(r.get("equity"))
            pos = st.get("positions") or []
            if eq:
                weights = {x["symbol"]: float(x.get("market_value") or 0) / eq for x in pos}
                cash = {"value": round(float(st.get("cash")) / eq, 4) if _num(st.get("cash")) is not None else NOT_COMPUTABLE,
                        "basis": "broker cash / equity"}
            holdings_source = "paper_accounts/pc_snapshot/state_latest.json"
            tail = tail_from_contributions(
                {x["symbol"]: _num(x.get("unrealized_pl")) for x in pos}, basis="unrealized_pl",
                note="share of the OPEN positions' P&L, not of the excess; realised P&L of "
                     "closed positions is not in it", min_abs=1.0)
            series = _series_from_nav(inputs.get("pc_nav") or [], px)
            manager_last = inputs.get("pc_manager_last_run")
        elif fam == "alpaca_fleet":
            fp = (inputs.get("fleet_positions") or {}).get(acct) or {}
            eq = _num(r.get("equity")) or _num(fp.get("equity"))
            pos = fp.get("positions") or []
            if eq and pos:
                weights = {x["symbol"]: x["market_value"] / eq for x in pos}
                holdings_source = fp.get("source")
                tail = tail_from_contributions({x["symbol"]: x.get("unrealized_pl") for x in pos},
                                               basis="unrealized_pl",
                                               note="share of the OPEN positions' P&L (fleet_daily read), "
                                                    "not of the excess; closed positions are not in it",
                                               min_abs=1.0)
            if eq and _num(r.get("cash")) is not None:
                cash = {"value": round(float(r["cash"]) / eq, 4), "basis": "broker cash / equity"}
            g = (inputs.get("fleet_grades") or {}).get(acct) or []
            series = [(d, a, s) for d, a, s in g]
            manager_last = (inputs.get("fleet_manager_last_run") or {}).get(acct)
        elif fam == "website_lane":
            lp = (inputs.get("lane_positions") or {}).get(acct)
            eq = _num(r.get("equity"))
            if lp and eq:
                mv, missing, cash_mv = {}, [], 0.0
                for t, sh in lp["positions"]:
                    if t in CASH_TICKERS:          # a dollar lot, never the listed ticker CASH
                        cash_mv += sh
                        continue
                    c = px.close_on_or_before(t, r.get("last_mark"))
                    if c == c:
                        mv[t] = mv.get(t, 0.0) + sh * c
                    else:
                        missing.append(t)
                weights = {t: v / eq for t, v in mv.items()}
                for t in missing:
                    weights.setdefault(t, float("nan"))
                holdings_source = lp["source"] + (f"; unpriced in the panel: {missing}" if missing else "")
                cash = ({"value": round(cash_mv / eq, 4), "basis": "the lane's CASH lot / equity"}
                        if cash_mv > 0 else
                        {"value": round(1 - sum(mv.values()) / eq, 4), "basis": "1 - priced MV / equity"}
                        if not missing else {"value": NOT_COMPUTABLE,
                                             "why": f"{len(missing)} holding(s) unpriced: {missing}"})
            tail = {"status": NOT_COMPUTABLE, "why": "lane lots reopen at every rebalance: the "
                    "positions route carries P&L since the last rebalance, not since inception"}
            series = _lane_series(receipt, acct)
        elif fam in ("night_books", "night_books_twin"):
            nav = (inputs.get("night_nav") or {}).get(r.get("book_id")) or []
            series = _series_from_nav(nav, px)
            if fam == "night_books_twin":
                e["twin_of"] = _twin_parent_night(r, rows)
            tail = {"status": NOT_COMPUTABLE, "why": "paper_books holdings are not read by book_dna v1"}
        elif fam == "murat_book":
            tail = {"status": NOT_COMPUTABLE, "why": "receipt row is a window return of unconfirmed "
                    "share counts (not a P&L); holdings not read by book_dna v1"}
        if fam.endswith("twin") and e["twin_of"] is None:
            e["twin_of"] = r.get("graded_against")
        e["sessions_graded"] = sessions
        e["holdings_source"] = holdings_source
        e["n_holdings"] = len([t for t in weights if t not in CASH_TICKERS]) or None
        e["tickers"] = sorted(t for t in weights if t not in CASH_TICKERS)
        e["weights"] = {t: (round(w, 5) if _num(w) is not None else None) for t, w in weights.items()}
        e["tail"] = tail
        top1 = (tail.get("top1") or {}).get("share") if tail.get("status") == "OK" else None
        e["one_name_dependence"] = (None if top1 is None else bool(top1 > p["one_name_share"]))
        e["concentration"] = concentration(weights, smap)
        e["beta_vs_spy"] = beta_of(series, p["min_beta_obs"])
        e["cash_fraction"] = cash
        e["n_series_periods"] = len(series)
        sub = subwindows(series, sessions)
        e["subwindows"] = sub
        e["fair_twin"] = fair_twin
        e["manager_last_run"] = manager_last
        e["manager_sessions_since"] = _sessions_since(px, manager_last, today)
        e["rule"] = rule_of.get(r.get("book_id"))
        e["_series"] = series
        out.append(e)
    # frozen replications: another non-twin book of the same rule that also qualifies
    by_rule: dict = {}
    for e in out:
        if e.get("rule") and not e["family"].endswith("twin"):
            by_rule.setdefault(e["rule"], []).append(e)
    for e in out:
        rep = None
        for o in by_rule.get(e.get("rule"), []):
            if o is e:
                continue
            if (o["sessions_graded"] or 0) >= p["early_min_sessions"] and (o["excess_pp"] or 0) > 0:
                rep = o["account"]
                break
        e["evidence"] = evidence_label(
            sessions=e["sessions_graded"], excess_pp=e["excess_pp"], sub=e["subwindows"],
            fair_twin_excess_pp=(e["fair_twin"] or {}).get("excess_over_twin_pp"),
            replicated_by=rep, p=p)
    return out


# ───────────────────────────── clusters ─────────────────────────────────────

class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _series_corr(a: list, b: list) -> tuple[Optional[float], int, bool]:
    da = {d: x for d, x, _ in a}
    db = {d: x for d, x, _ in b}
    common = sorted(set(da) & set(db))
    if len(common) < 2:
        return None, len(common), False
    xa = np.array([da[d] for d in common])
    xb = np.array([db[d] for d in common])
    identical = bool(np.allclose(xa, xb, atol=1e-9, rtol=0))
    if np.std(xa) == 0 or np.std(xb) == 0:
        return None, len(common), identical
    return float(np.corrcoef(xa, xb)[0, 1]), len(common), identical


def cluster(books: list[dict], *, jaccard_threshold: float, corr_threshold: float,
            min_corr_obs: int) -> tuple[list[list[int]], list[dict]]:
    """Single-linkage components. Edges: holdings Jaccard >= threshold (both books
    have holdings), return correlation >= threshold on >= min_corr_obs common
    periods, or IDENTICAL period returns on >= 2 common periods."""
    n = len(books)
    uf = _UF(n)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = books[i], books[j]
            why = None
            if a.get("tickers") and b.get("tickers"):
                jac = jaccard(a["tickers"], b["tickers"])
                if jac >= jaccard_threshold:
                    why = f"jaccard {jac:.2f}"
            if why is None and a.get("_series") and b.get("_series"):
                c, nc, ident = _series_corr(a["_series"], b["_series"])
                if ident:
                    why = f"identical returns on {nc} periods"
                elif c is not None and nc >= min_corr_obs and c >= corr_threshold:
                    why = f"corr {c:.2f} on {nc} periods"
            if why:
                uf.union(i, j)
                edges.append({"a": a["account"], "b": b["account"], "why": why})
    comps: dict = {}
    for i in range(n):
        comps.setdefault(uf.find(i), []).append(i)
    return sorted(comps.values(), key=lambda c: (-len(c), c[0])), edges


def _basket(members: list[dict], top: int) -> list[dict]:
    cnt: dict = {}
    wsum: dict = {}
    for m in members:
        for t in m.get("tickers") or []:
            cnt[t] = cnt.get(t, 0) + 1
            wsum[t] = wsum.get(t, 0.0) + float((m.get("weights") or {}).get(t) or 0.0)
    ranked = sorted(cnt, key=lambda t: (-cnt[t], -wsum[t], t))
    with_h = sum(1 for m in members if m.get("tickers"))
    return [{"ticker": t, "n_books": cnt[t], "share_of_books": round(cnt[t] / with_h, 3)}
            for t in ranked[:top] if cnt[t] >= 2 or len(members) == 1]


# ───────────────────────────── lanes ────────────────────────────────────────

def lanes_block(receipt: dict, books: list[dict], inputs: dict, p: dict) -> dict:
    lanes = [b for b in books if b["family"] == "website_lane"]
    if not lanes:
        return {"status": NOT_COMPUTABLE, "why": "no priced website lanes"}
    names = [b["account"] for b in lanes]
    mat: dict = {}
    for a in lanes:
        mat[a["account"]] = {}
        for b in lanes:
            c, nc, _ = _series_corr(a["_series"], b["_series"])
            mat[a["account"]][b["account"]] = (None if c is None or nc < p["min_corr_obs"]
                                               else round(c, 3))
    uf = _UF(len(names))
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            c = mat[names[i]][names[j]]
            if c is not None and c >= p["lane_family_corr"]:
                uf.union(i, j)
    fams: dict = {}
    for i in range(len(names)):
        fams.setdefault(uf.find(i), []).append(names[i])
    families = []
    for mem in sorted(fams.values(), key=lambda m: (-len(m), m[0])):
        cs = [mat[a][b] for a in mem for b in mem if a < b and mat[a][b] is not None]
        families.append({"members": mem, "n": len(mem),
                         "pairwise_corr_range": [min(cs), max(cs)] if cs else None,
                         "reading": ("ONE risk dial: same signal family at different sizing"
                                     if len(mem) > 1 else "distinct")})
    caps = inputs.get("lane_caps") or {}

    def capstr(lane: str) -> str:
        if lane not in caps:
            return "UNKNOWN (no loaded lane config names it)"
        v = caps[lane].get("max_single_name")
        return "NONE declared" if v is None else f"{float(v):.0%}"

    def t1(x: dict) -> str:
        c = x.get("concentration") or {}
        tw = c.get("top1_weight_of_invested") or c.get("top1_weight_of_equity") or {}
        return f"{tw.get('ticker')} {tw.get('weight', 0):.1%}" if tw else "n/a"

    held = [b for b in lanes if b["tickers"]]
    uf2 = _UF(len(held))
    jac: dict = {}
    for i in range(len(held)):
        for j in range(i + 1, len(held)):
            v = jaccard(held[i]["tickers"], held[j]["tickers"])
            jac[(i, j)] = v
            if v >= p["lane_identity_jaccard"]:
                uf2.union(i, j)
    groups: dict = {}
    for i in range(len(held)):
        groups.setdefault(uf2.find(i), []).append(i)
    ident = []
    for idx in groups.values():
        if len(idx) < 2:
            continue
        mem = [held[i] for i in idx]
        js = [jac[(a, b)] for a in idx for b in idx if a < b]
        names_u = set().union(*[set(m["tickers"]) for m in mem])
        who = ", ".join(m["account"] for m in mem)
        ident.append({
            "lanes": [m["account"] for m in mem],
            "pairwise_jaccard_range": [round(min(js), 3), round(max(js), 3)],
            "n_names_union": len(names_u),
            "declared_max_single_name": {m["account"]: capstr(m["account"]) for m in mem},
            "cap_source": {m["account"]: (caps.get(m["account"]) or {}).get("source") for m in mem},
            "top1_weight_now": {m["account"]: t1(m) for m in mem},
            "excess_pp": {m["account"]: m["excess_pp"] for m in mem},
            "statement": (f"{who} hold the same names ({len(names_u)} in the union; pairwise Jaccard "
                          f"{min(js):.2f}-{max(js):.2f}): they differ in treatment, not selection. "
                          f"Declared max_single_name: "
                          + "; ".join(f"{m['account']} {capstr(m['account'])}" for m in mem)
                          + ". Top-1 now: " + "; ".join(f"{m['account']} {t1(m)}" for m in mem) + "."),
        })
    return {"status": "OK", "correlation_matrix": mat, "families": families,
            "identity_statements": ident,
            "n_lanes": len(names), "n_independent_lane_families": len(families)}


# ───────────────────────────── losers ───────────────────────────────────────

def classify_loser(b: dict, p: dict) -> dict:
    """The declared rule order (config): control_artifact -> unmanaged ->
    sizing_concentration -> timing_exit -> selection; not_determinable when the
    evidence for every rule is missing."""
    if b["family"].endswith("twin"):
        return {"error_type": "control_artifact",
                "why": f"a control twin of {b.get('twin_of')}: informative about the control, not a strategy"}
    ms = b.get("manager_sessions_since")
    if ms is not None and ms > p["unmanaged_sessions"]:
        return {"error_type": "unmanaged",
                "why": f"no manager run in {ms} sessions (last {str(b.get('manager_last_run'))[:19]})"}
    t = b.get("tail") or {}
    if t.get("status") == "OK" and (t.get("total") or 0) < 0:
        s1 = t["top1"]["share"]
        if s1 > p["loser_sizing_share"]:
            return {"error_type": "sizing_concentration",
                    "why": f"{t['top1']['ticker']} carries {s1:.0%} of the loss ({t['basis']})"}
    elif t.get("status") != "OK":
        c = b.get("concentration") or {}
        tw = c.get("top1_weight_of_invested") or c.get("top1_weight_of_equity") or {}
        if tw and float(tw.get("weight") or 0) >= p["loser_weight_fallback"]:
            return {"error_type": "sizing_concentration",
                    "why": (f"by WEIGHT, not by P&L share (not computable: {t.get('why')}): "
                            f"{tw['ticker']} is {float(tw['weight']):.0%} of the book now")}
    sub = b.get("subwindows") or {}
    if sub.get("status") == "OK" and (b.get("excess_pp") or 0) < 0:
        w = sub["windows"]
        tot = sum(x["excess_pp"] for x in w)
        worst = min(w, key=lambda x: x["excess_pp"])
        if tot < 0 and worst["excess_pp"] < 0 and worst["excess_pp"] / tot >= p["timing_share"]:
            return {"error_type": "timing_exit",
                    "why": f"{worst['excess_pp'] / tot:.0%} of the shortfall in {worst['from']}..{worst['to']}"}
    if t.get("status") == "OK" or (b.get("concentration") or {}).get("status") == "OK":
        return {"error_type": "selection", "why": "loss not concentrated in one name or one third of the window"}
    return {"error_type": "not_determinable",
            "why": f"no holdings P&L and no full-window series ({t.get('why') or sub.get('why')})"}


# ───────────────────────────── the receipt ──────────────────────────────────

def _public(b: dict) -> dict:
    return {k: v for k, v in b.items() if not k.startswith("_")}


def build(receipt: dict, inputs: dict, px: Prices, *, today: Optional[date] = None,
          prices_source: str = "") -> dict:
    p = params()
    today = today or date.today()
    books = book_rows(receipt, inputs, px, p, today)
    ahead = [b for b in books if (b["excess_pp"] or 0) > 0 and b["excess_pp"] is not None]
    nt = [b for b in ahead if not b["family"].endswith("twin")]
    comps, edges = cluster(nt, jaccard_threshold=p["jaccard_threshold"],
                           corr_threshold=p["corr_threshold"], min_corr_obs=p["min_corr_obs"])
    clusters = []
    for k, idx in enumerate(comps):
        mem = [nt[i] for i in idx]
        ex = [m["excess_pp"] for m in mem]
        clusters.append({"cluster_id": k, "n": len(mem), "members": [m["account"] for m in mem],
                         "families": sorted({m["family"] for m in mem}),
                         "n_with_holdings": sum(1 for m in mem if m["tickers"]),
                         "shared_basket": _basket(mem, p["basket_top"]),
                         "excess_pp_mean": round(float(np.mean(ex)), 3),
                         "excess_pp_median": round(float(np.median(ex)), 3)})
    sens = {}
    for thr in p["jaccard_sensitivity"]:
        cs, _ = cluster(nt, jaccard_threshold=thr, corr_threshold=p["corr_threshold"],
                        min_corr_obs=p["min_corr_obs"])
        sens[f"{thr:.2f}"] = len(cs)
    twins_ahead = [b for b in ahead if b["family"].endswith("twin")]
    cl_of = {a: c["cluster_id"] for c in clusters for a in c["members"]}
    losers = sorted([b for b in books if b["excess_pp"] is not None],
                    key=lambda b: b["excess_pp"])[:p["n_losers"]]
    loser_rows = []
    for b in losers:
        row = _public(b)
        row.update(classify_loser(b, p))
        loser_rows.append(row)
    summary = summarise(len(ahead), len(nt), clusters, p, sens)
    return {
        "schema": SCHEMA, "receipt": "book_dna", "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roi_receipt_run_id": receipt.get("run_id"),
        "roi_receipt_generated_utc": receipt.get("generated_utc"),
        "params": p, "label_ceiling": LABEL_CEILING,
        "sources": {"prices": prices_source, "sector_map": inputs.get("sector_source"),
                    "gaps": inputs.get("gaps") or {}},
        "summary": summary,
        "clusters": clusters, "cluster_edges": edges,
        "cluster_count_sensitivity": sens,
        "twins_ahead": {"n": len(twins_ahead),
                        "n_whose_parent_is_ahead": sum(1 for t in twins_ahead if t.get("twin_of") in cl_of),
                        "by_parent": _count_by(twins_ahead, "twin_of")},
        "lanes": lanes_block(receipt, books, inputs, p),
        "books": [_public(b) for b in books],
        "losers": loser_rows,
        "read_me_first": ("A count of books ahead of SPY is not a count of bets: twins re-price a "
                          "parent, and books holding the same names are one exposure. Every label "
                          "here is at most REPLICATED; most rows are OBSERVED(n) over a handful of "
                          "sessions. Nothing here is a claim."),
    }


def _count_by(rows: list, key: str) -> dict:
    out: dict = {}
    for r in rows:
        k = str(r.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def summarise(n_raw: int, n_nt: int, clusters: list, p: dict,
              sensitivity: Optional[dict] = None) -> dict:
    k = len(clusters)
    big = clusters[0] if clusters else None
    basket = [x["ticker"] for x in (big or {}).get("shared_basket") or []]
    share = (big["n"] / n_nt) if big and n_nt else None
    s = {"n_ahead_raw": n_raw, "n_ahead_non_twin": n_nt,
         "n_independent_clusters_ahead": k,
         "collapse_factor": round(n_raw / k, 2) if k else None,
         "largest_cluster_share": None if share is None else round(share, 3),
         "largest_cluster_size": big["n"] if big else 0,
         "largest_cluster_basket": basket,
         "largest_cluster_members_sample": (big or {}).get("members", [])[:5],
         "jaccard_threshold": p["jaccard_threshold"],
         "cluster_count_sensitivity": dict(sensitivity or {}),
         "book_dna_status": "OK"}
    s["collapse_line"] = collapse_line(s)
    return s


def collapse_line(s: dict) -> str:
    """THE line. Never print `n_ahead` without it."""
    if s.get("book_dna_status") != "OK":
        return (f"{s.get('n_ahead_raw', '?')} ahead of SPY: collapse NOT COMPUTED "
                f"({s.get('why') or 'book_dna did not run on this receipt'}) -- "
                f"the count is NOT a count of independent bets")
    if s.get("n_ahead_raw", 0) == 0:
        return "0 ahead of SPY = 0 non-twin = 0 independent clusters"
    bs = s.get("largest_cluster_basket") or []
    name = (", ".join(bs) if bs else
            f"{(s.get('largest_cluster_members_sample') or ['?'])[0]} (no shared holdings)")
    sh = s.get("largest_cluster_share")
    line = (f"{s['n_ahead_raw']} ahead of SPY = {s['n_ahead_non_twin']} non-twin = "
            f"{s['n_independent_clusters_ahead']} independent clusters; largest cluster = "
            f"{name} ({'n/a' if sh is None else f'{100 * sh:.0f}%'})")
    sens = s.get("cluster_count_sensitivity") or {}
    if len(sens) > 1:
        ks = sorted(sens)
        line += (f" [Jaccard {s.get('jaccard_threshold'):.2f}; clusters "
                 + ", ".join(f"{sens[k]} at {k}" for k in ks) + "]")
    return line


def refused_summary(n_ahead_raw: Any, why: str) -> dict:
    s = {"n_ahead_raw": n_ahead_raw, "n_ahead_non_twin": None,
         "n_independent_clusters_ahead": None, "collapse_factor": None,
         "largest_cluster_share": None, "largest_cluster_basket": [],
         "book_dna_status": "REFUSED", "why": why[:300]}
    s["collapse_line"] = collapse_line(s)
    return s


def write(dna: dict, out_dir: Path, run_id: str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"book_dna_{run_id}.json"
    n = 2
    while p.exists():                     # never overwrite a receipt
        p = out_dir / f"book_dna_{run_id}_{n}.json"
        n += 1
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dna, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)
    return p


def run(receipt: dict, *, out_dir: Path = PA_DIR, run_id: str, bars: Optional[pd.DataFrame] = None,
        inputs: Optional[dict] = None, http_get: Optional[Callable] = None,
        fetch_lanes: bool = True, today: Optional[date] = None) -> tuple[dict, Path]:
    """Load, build, write. Raises on failure: the caller turns that into a REFUSED
    summary on the ROI receipt (never a silent absence)."""
    inputs = inputs if inputs is not None else load_inputs(receipt, http_get=http_get,
                                                            fetch_lanes=fetch_lanes)
    syms: set = set()
    for b in inputs.get("books") or []:
        syms |= {str(x.get("ticker")) for x in b.get("positions") or [] if x.get("ticker")}
    for v in (inputs.get("lane_positions") or {}).values():
        syms |= {t for t, _ in v["positions"] if t not in CASH_TICKERS}
    px, src = load_prices(syms, bars=bars)
    if not px.has("SPY"):
        raise RuntimeError(f"no SPY bars ({src}): sessions, sub-windows and beta all need it")
    dna = build(receipt, inputs, px, today=today, prices_source=src)
    path = write(dna, out_dir, run_id)
    dna["summary"]["book_dna_receipt"] = path.name
    return dna, path


__all__ = ["SCHEMA", "LABEL_LADDER", "LABEL_CEILING", "ERROR_TYPES", "NOT_COMPUTABLE",
           "Prices", "build", "classify_loser", "cluster", "collapse_line", "evidence_label",
           "jaccard", "lanes_block", "load_inputs", "params", "refused_summary", "run",
           "summarise", "tail_from_contributions", "write"]
