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
* per book (CH-11 note, 2026-11-13): `market_exposure` -- up-capture, down-capture,
  the beta-adjusted excess (return - beta x SPY leg) and the residual by month, from
  the same series as the beta; CANNOT DETERMINE with a reason when it is not answerable;
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

import bisect
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _config

SCHEMA = "book_dna/1"
NOT_COMPUTABLE = "NOT_COMPUTABLE"
#: a number that computes but is not believed (C15: beta on a date-stamp-lagged series)
NOT_CREDIBLE = "NOT_CREDIBLE"
#: CH-11 note (2026-11-13): a market-exposure field that cannot be answered (series too
#: short, beta not credible, no SPY leg) -- printed with its reason, never 0 or blank.
CANNOT_DETERMINE = "CANNOT DETERMINE"
#: The ladder from roadmap section 7. This module may award only the first three.
LABEL_LADDER = ("OBSERVED", "EARLY_EVIDENCE", "REPLICATED", "VALIDATED_EDGE")
LABEL_CEILING = "REPLICATED"
ERROR_TYPES = ("control_artifact", "decomposed", "unmanaged", "sizing_concentration",
               "timing_exit", "selection", "not_determinable")
#: Review F4: the loser rules, in the order they are tried, printed on the receipt.
LOSER_RULE_ORDER = (
    "control_artifact: a twin or a kind=control book",
    "decomposed: a lane in an identity group (same names): the group's best excess is the "
    "common shortfall (selection), the member's gap to it is treatment/sizing",
    "unmanaged: no manager run in BOOK_DNA_UNMANAGED_SESSIONS sessions",
    "coverage gate: the P&L this module can see must explain >= BOOK_DNA_LOSS_COVERAGE_MIN of "
    "the shortfall, else no P&L rule may fire",
    "sizing_concentration: top-1 > BOOK_DNA_LOSER_SIZING_SHARE of the same-direction loss",
    "timing_exit: the worst third >= BOOK_DNA_TIMING_SHARE of the GROSS negative sub-window loss",
    "selection: a covered loss spread across names (a positive finding, never the fall-through)",
    "sizing_concentration by WEIGHT: no P&L share computable and top-1 weight >= "
    "BOOK_DNA_LOSER_WEIGHT_FALLBACK",
    "not_determinable: none of the above has evidence; the coverage ratio is printed",
)
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
        "min_capture_obs": int(_cfg("BOOK_DNA_MIN_CAPTURE_OBS", 8)),
        "stamp_month_min_obs": int(_cfg("BOOK_DNA_STAMP_MONTH_MIN_OBS", 8)),
        "stamp_month_min_lag_corr": float(_cfg("BOOK_DNA_STAMP_MONTH_MIN_LAG_CORR", 0.30)),
        "stamp_month_gap_se": float(_cfg("BOOK_DNA_STAMP_MONTH_GAP_SE", 1.0)),
        "exposure_min_cover": float(_cfg("BOOK_DNA_EXPOSURE_MIN_COVER", 0.80)),
        "exposure_max_return_gap_pp": float(_cfg("BOOK_DNA_EXPOSURE_MAX_RETURN_GAP_PP", 2.0)),
        "max_capture_se": float(_cfg("BOOK_DNA_MAX_CAPTURE_SE", 0.25)),
        "mde_z": float(_cfg("BOOK_DNA_MDE_Z", 2.8)),
        "rf_annual_assumed": float(_cfg("BOOK_DNA_RF_ANNUAL_ASSUMED", 0.04)),
        "early_min_sessions": int(_cfg("BOOK_DNA_EARLY_MIN_SESSIONS", 21)),
        "fair_twin_kinds": list(_cfg("BOOK_DNA_FAIR_TWIN_KINDS",
                                     ("matched_twin21", "matched_random", "random_same_band"))),
        "one_name_share": float(_cfg("BOOK_DNA_ONE_NAME_SHARE", 0.50)),
        "one_name_min_excess_pp": float(_cfg("BOOK_DNA_ONE_NAME_MIN_EXCESS_PP", 1.0)),
        "one_name_max_recon_gap_pp": float(_cfg("BOOK_DNA_ONE_NAME_MAX_RECON_GAP_PP", 0.25)),
        "loss_coverage_min": float(_cfg("BOOK_DNA_LOSS_COVERAGE_MIN", 0.80)),
        "exante_sessions": int(_cfg("BOOK_DNA_EXANTE_SESSIONS", 150)),
        "loser_rule_order": list(LOSER_RULE_ORDER),
        "n_losers": int(_cfg("BOOK_DNA_N_LOSERS", 10)),
        "unmanaged_sessions": int(_cfg("BOOK_DNA_UNMANAGED_SESSIONS", 5)),
        "loser_sizing_share": float(_cfg("BOOK_DNA_LOSER_SIZING_SHARE", 0.40)),
        "timing_share": float(_cfg("BOOK_DNA_TIMING_SHARE", 0.70)),
        "loser_weight_fallback": float(_cfg("BOOK_DNA_LOSER_WEIGHT_FALLBACK", 0.20)),
        "lane_family_corr": float(_cfg("BOOK_DNA_LANE_FAMILY_CORR", 0.85)),
        "lane_identity_jaccard": float(_cfg("BOOK_DNA_LANE_IDENTITY_JACCARD", 0.90)),
        "basket_top": int(_cfg("BOOK_DNA_BASKET_TOP", 5)),
        "flag_idle_gross": float(_cfg("BOOK_DNA_FLAG_IDLE_GROSS", 0.05)),
        "flag_idle_min_sessions": int(_cfg("BOOK_DNA_FLAG_IDLE_MIN_SESSIONS", 5)),
        "flag_from_cash_share": float(_cfg("BOOK_DNA_FLAG_FROM_CASH_SHARE", 0.5)),
        "flag_same_bet_corr": float(_cfg("BOOK_DNA_FLAG_SAME_BET_CORR", 0.90)),
        "flag_same_bet_min_obs": int(_cfg("BOOK_DNA_FLAG_SAME_BET_MIN_OBS", 20)),
        "flag_mde_min_obs": int(_cfg("BOOK_DNA_FLAG_MDE_MIN_OBS", 20)),
        "flag_one_name_share": float(_cfg("BOOK_DNA_FLAG_ONE_NAME_SHARE", 0.40)),
        "flag_high_beta": float(_cfg("BOOK_DNA_FLAG_HIGH_BETA", 1.5)),
        "flag_control_name_markers": list(_cfg("RESULTS_VOICE_CONTROL_NAME_MARKERS",
                                               ("_random_twin", "comparato", "__", "-control"))),
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
            # review m6 (PR #140): a parquet filter, never the whole deep panel in RAM
            b = xs_ranker.load_bars(symbols=sorted(want))
            frames.append(b[b["symbol"].isin(want)])
            srcs.append("xs_ranker.load_bars(symbols=)")
        except Exception as e:                      # a missing panel is a named gap
            srcs.append(f"xs_ranker.load_bars() FAILED: {type(e).__name__}: {e}"[:200])
        g = LLM_DIR / "global_bars.parquet"
        if g.exists():
            try:
                gb = pd.read_parquet(g, columns=["symbol", "date", "open", "close"],
                                     filters=[("symbol", "in", sorted(want))])
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


def _night_decisions(conn: Any, gaps: dict) -> Optional[dict]:
    """{book_id: [(asof_date, {ticker: weight})]} from paper_book_decisions, oldest first.
    None (with a gap) when the table cannot be read -- never {} for "could not read", because
    {} means "no book ever decided" and that is what NEVER_INVESTED would then report."""
    try:
        rows = conn.execute("SELECT book_id, asof_date, weights_json FROM paper_book_decisions "
                            "ORDER BY book_id, asof_date").fetchall()
    except Exception as e:                       # noqa: BLE001 -- a named gap, never raised
        gaps["paper_book_decisions"] = f"{type(e).__name__}: {e}"[:200]
        return None
    out: dict = {}
    for r in rows:
        try:
            w = json.loads(r[2] or "{}")
        except ValueError:
            gaps[f"paper_book_decisions/{r[0]}/{r[1]}"] = "weights_json unreadable"
            continue
        if isinstance(w, dict):
            out.setdefault(str(r[0]), []).append((str(r[1])[:10], {str(k): _num(v) for k, v in w.items()}))
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
                fetch_lanes: bool = True, read_only_db: bool = False) -> dict:
    """Read every holdings / series source this module uses. Each source that
    fails is recorded in `inputs["gaps"]`, never raised. `read_only_db=True` (an
    out-of-band rebuild against the live data root) opens the paper-books database
    with `mode=ro` instead of through `init_db`."""
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
    # flags (claims-none 2026-11-14): gross / equity at EVERY fleet_daily read, dated by the
    # read's own stamp (never the file's mtime), so IDLE_CASH can say since when
    fg: dict = {}
    for f in fd:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            gaps[f"fleet_daily/{f.name}"] = "unreadable"
            continue
        sess = _session_date_of_stamp(str(d.get("stamp_utc") or ""))
        if not sess:
            continue
        for a in d.get("accounts") or []:
            g = _num(a.get("gross_over_equity"))
            if a.get("status") == "ok" and g is not None:
                fg.setdefault(a.get("role"), {})[sess] = g
    inp["fleet_gross"] = {r: sorted(v.items()) for r, v in fg.items()}
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
    pcg: dict = {}
    last_t = None
    for r in _read_jsonl(PC_NAV):
        last_t = r.get("t") or last_t
        d = _session_date_of_stamp(r.get("t") or "")
        if d and r.get("equity") is not None:
            pcn[d] = float(r["equity"])
            eqv, lm, sm = _num(r.get("equity")), _num(r.get("long_market_value")), _num(r.get("short_market_value"))
            if eqv and lm is not None:
                pcg[d] = (abs(lm) + abs(sm or 0.0)) / eqv
            elif r.get("n_positions") == 0:
                pcg[d] = 0.0
    inp["pc_nav"] = sorted(pcn.items())
    inp["pc_gross"] = sorted(pcg.items())
    inp["pc_manager_last_run"] = last_t
    # night books
    try:
        from backend.services import paper_books as PB
        if read_only_db:
            # a reader must not run init_db (schema DDL) against the live database
            import sqlite3
            from backend import db as _db
            # claims-none (2026-11-14): with no WAL content there is nothing a mode=ro open could
            # read that the main file lacks, so open it immutable -- mode=ro CREATED an empty -wal
            # and a -shm beside the live database on the 2026-11-14 rebuild. With a non-empty WAL,
            # mode=ro (immutable would miss the rows still in it; it only moves the -shm mtime).
            dbp = Path(_db.DB_PATH)
            wal = dbp.with_name(dbp.name + "-wal")
            imm = not wal.exists() or wal.stat().st_size == 0
            ro = sqlite3.connect(f"file:{dbp.as_posix()}?{'immutable=1' if imm else 'mode=ro'}", uri=True)
            inp["db_open_mode"] = "immutable=1 (no WAL content)" if imm else "mode=ro (WAL present)"
            ro.row_factory = sqlite3.Row
            try:
                inp["night_nav"] = PB.nav_series(conn=ro)
                inp["night_decisions"] = _night_decisions(ro, gaps)
            finally:
                ro.close()
        else:
            inp["night_nav"] = PB.nav_series()
            c = PB._conn()
            try:
                inp["night_decisions"] = _night_decisions(c, gaps)
            finally:
                c.close()
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
    # C15 (2026-10-07; review C3 F9): a lane whose NAV is stamped a session late correlates
    # with YESTERDAY's SPY better than today's, and its same-day beta (0.03-0.07 for equity
    # lanes) is then an artefact of the date stamp, not a property of the book. Lag -1 = the
    # book's period return against the PREVIOUS period's SPY return.
    lag = None
    if len(pts) >= max(min_obs, 3) + 1 and np.std(y[1:]) > 0 and np.std(x[:-1]) > 0:
        lag = float(np.corrcoef(x[:-1], y[1:])[0, 1])
    out = {"value": round(beta, 3), "corr_vs_spy": None if corr is None else round(corr, 3),
           "corr_vs_spy_lag_minus_1": None if lag is None else round(lag, 3), "n_obs": len(pts)}
    if lag is not None and (corr is None or lag > corr):
        out.update(value=NOT_CREDIBLE, beta_same_day=round(beta, 3),
                   why=(f"beta: NOT_CREDIBLE (date stamp lag): corr vs SPY lag -1 "
                        f"{lag:+.2f} beats same-day {(corr if corr is not None else float('nan')):+.2f} "
                        f"over {len(pts)} periods; the series looks stamped a period late"))
    return out


def _cd(why: str, **extra: Any) -> dict:
    return {"value": CANNOT_DETERMINE, "why": why, **extra}


_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


def stamp_screen(series: Optional[list], *, min_month_obs: int, min_lag_corr: float, gap_se: float,
                 spy_close: Optional[dict] = None) -> tuple[dict, list]:
    """CH-11 fix B1 (review of PR #140): the C15 date-stamp test per CALENDAR MONTH.

    `beta_of` compares lag -1 with same-day correlation over the whole series. A series
    stamped a session late in one stretch and on the right day in another (the website
    lanes: late June-August, right from September) averages out and passes. Here each
    month with >= `min_month_obs` periods is tested on its own: it FAILS when
    corr(book_t, SPY lagged) >= `min_lag_corr` AND atanh(corr lagged) - atanh(corr same
    period) > `gap_se` x sqrt(2/(n-3)) -- the lag is the better alignment by at least that
    many standard errors, and it is material. A detection rule, not a 5% test (a month has
    too few periods for one); each month prints both correlations and the SE of the gap.
    Returns (the check, the periods to estimate on): every period after the LAST failing
    month, or the whole series when no month fails. Dates are never shifted: a lagged
    stretch is dropped, and the row says which months and why.

    "SPY lagged" for a period (d_prev, d] is SPY over the same sessions shifted back one
    session, read from `spy_close` (date -> close). Without it, the previous PERIOD's SPY
    return stands in -- which is the wrong number after a multi-session gap: on the lanes'
    August (16 periods, several gaps) it gave lag -1 corr +0.21 where SPY's own previous
    session gives about +0.6, and the lag went unseen."""
    pts = [(str(d), float(b), float(s)) for d, b, s in series or []
           if _num(b) is not None and _num(s) is not None]
    cal = sorted(k for k, v in (spy_close or {}).items() if _num(v) is not None and _ISO_DAY.match(str(k)))
    pos = {d: i for i, d in enumerate(cal)}
    months: dict = {}
    n_unpriced = 0
    for i in range(1, len(pts)):
        if cal:
            a, b = pos.get(pts[i - 1][0][:10]), pos.get(pts[i][0][:10])
            if a is None or b is None or a < 1 or b <= a:
                n_unpriced += 1
                continue
            lagged = float(spy_close[cal[b - 1]]) / float(spy_close[cal[a - 1]]) - 1.0
        else:
            lagged = pts[i - 1][2]
        months.setdefault(pts[i][0][:7], []).append((pts[i][1], pts[i][2], lagged))
    rows, failing = [], []
    for m, v in sorted(months.items()):
        n = len(v)
        row: dict = {"month": m, "n_periods": n}
        y = np.array([q[0] for q in v])
        x0 = np.array([q[1] for q in v])
        xm = np.array([q[2] for q in v])
        if n < max(min_month_obs, 4):
            row["status"] = "not tested: too few periods"
        elif min(np.std(y), np.std(x0), np.std(xm)) == 0:
            row["status"] = "not tested: a constant series"
        else:
            c0 = float(np.corrcoef(y, x0)[0, 1])
            c1 = float(np.corrcoef(y, xm)[0, 1])
            gap = float(np.arctanh(np.clip(c1, -0.999, 0.999)) - np.arctanh(np.clip(c0, -0.999, 0.999)))
            fail = c1 >= min_lag_corr and gap > gap_se * math.sqrt(2.0 / (n - 3))
            row.update(corr_same_day=round(c0, 3), corr_lag_minus_1=round(c1, 3),
                       z_gap=round(gap, 3), z_gap_se=round(math.sqrt(2.0 / (n - 3)), 3))
            row["status"] = "FAIL: lag -1 beats same-day" if fail else "ok"
            if fail:
                failing.append(m)
        rows.append(row)
    check = {"method": (f"per calendar month with >= {min_month_obs} periods: FAIL when atanh(corr vs SPY "
                        f"shifted back one session) >= {min_lag_corr} and atanh(that) - atanh(corr vs SPY "
                        f"same period) > {gap_se:g} x sqrt(2/(n-3)) (a detection rule, not a 5% test); "
                        f"lagged SPY from {'SPY session closes' if cal else 'the previous period (no calendar)'}; "
                        "exposure is estimated after the last failing month; dates are never shifted"),
             "months": rows, "failing_months": failing, "n_periods_without_a_lagged_spy": n_unpriced}
    if not failing:
        return check, list(series or [])
    kept = [q for q in series or [] if str(q[0])[:7] > failing[-1]]
    check.update(kept_from=kept[0][0] if kept else None, kept_periods=len(kept),
                 dropped_periods=len(series or []) - len(kept))
    return check, kept


def _session_spans(series: list, session_dates: Optional[list]) -> list:
    """Sessions each period spans (None = unknown: the first period, a non-ISO date, or
    no calendar). m4: capture uses one-session periods, so a 4-session gap is not
    averaged in as if it were one day."""
    if not session_dates or not series:
        return [None] * len(series or [])
    sd = sorted({str(d)[:10] for d in session_dates})
    out: list = [None]
    for i in range(1, len(series)):
        a, b = str(series[i - 1][0])[:10], str(series[i][0])[:10]
        if not (_ISO_DAY.match(a) and _ISO_DAY.match(b)):
            out.append(None)
            continue
        out.append(bisect.bisect_right(sd, b) - bisect.bisect_right(sd, a))
    return out


def _capture(pts: list, side: str, min_obs: int, max_se: Optional[float] = None) -> dict:
    """Mean book period return / mean SPY period return over the periods where SPY
    went `side` (up: > 0, down: < 0). Down-capture < 1 = the book lost less than SPY
    on SPY's down periods; > 1 = it lost more. M2: its standard error by the delta
    method, SE = sd(r_book - c x r_SPY) / (sqrt(n) x |mean r_SPY|); above `max_se`
    the capture is CANNOT DETERMINE (the estimate and SE are kept, labelled)."""
    sel = [(b, s) for b, s in pts if (s > 0 if side == "up" else s < 0)]
    if len(sel) < min_obs:
        return {**_cd(f"{len(sel)} SPY-{side} periods < {min_obs}"), "n_periods": len(sel)}
    sb = np.array([b for b, _ in sel])
    ss = np.array([s for _, s in sel])
    ms, mb = float(ss.mean()), float(sb.mean())
    c = mb / ms
    se = float(np.std(sb - c * ss, ddof=1) / (math.sqrt(len(sel)) * abs(ms))) if len(sel) > 1 else float("inf")
    base = {"n_periods": len(sel), "mean_book_pct": round(100 * mb, 4), "mean_spy_pct": round(100 * ms, 4),
            "estimate": round(c, 3), "se": round(se, 3)}
    if max_se is not None and se > max_se:
        return {**base, **_cd(f"estimate {c:.2f} with SE {se:.2f} > {max_se:.2f} over {len(sel)} SPY-{side} "
                              f"periods: cannot be told apart from noise")}
    return {**base, "value": round(c, 3)}


def market_exposure(series: Optional[list], beta: dict, *, return_pct: Any, spy_leg_pct: Any,
                    min_capture_obs: Optional[int] = None, sessions: Optional[int] = None,
                    window: Optional[tuple] = None, session_dates: Optional[list] = None,
                    spy_close: Optional[dict] = None, p: Optional[dict] = None) -> dict:
    """CH-11 note (2026-11-13): how much of a book's return is plain SPY exposure.

    From the book's period-return series (the one `beta_of` used): beta with its SE,
    up-capture and down-capture with SE and n, the beta-adjusted excess over the
    receipt's own window (`return - beta x SPY leg`, beside the raw excess
    `return - SPY leg`) with SE and MDE, and the residual `r_book - beta x r_SPY`
    compounded per calendar month. rf = 0 by declaration (the row prints what an assumed
    cash rate would change), and the beta is in-sample: a description of the book's
    exposure, not a forecast of it.

    Fix round (review of PR #140):
    * B1 -- `stamp_screen` runs the date-stamp test per month; when a month fails, the
      beta and captures are estimated only after the last failing month and the row says so.
    * M1 -- the beta's window must cover >= `exposure_min_cover` of the receipt sessions
      and reproduce the receipt return within `exposure_max_return_gap_pp`; otherwise the
      receipt-window beta-adjusted excess is CANNOT DETERMINE ("not comparable") and the
      beta window's own figure is printed with its window.
    * M2 -- capture SE gate; m1 -- a flat NAV is CANNOT DETERMINE, never 0.00 / -0.00.
    A beta that is NOT_COMPUTABLE, or NOT_CREDIBLE with no clean trailing window, makes
    every field CANNOT DETERMINE with that reason."""
    q = params() if p is None else p
    mco = int(q["min_capture_obs"] if min_capture_obs is None else min_capture_obs)
    method = ("beta: OLS slope of book period returns on SPY period returns (same periods), SE from the "
              "OLS residuals; capture: mean book / mean SPY return over one-session SPY-up (SPY-down) "
              "periods, SE by the delta method (arithmetic per-period convention; "
              "benchmark_analytics._compute_capture_ratios is monthly-geometric and needs >= 6 months); "
              "beta-adjusted excess: receipt return - beta x receipt SPY leg, SE = sqrt(n var(r_book - "
              "beta r_SPY) + SE(beta)^2 SPY leg^2) over the n beta-window periods (iid periods), "
              f"MDE = {q['mde_z']} x SE; by month: compound(1 + r_book - beta x r_SPY) - 1; rf = 0 declared")
    bval = beta.get("value") if isinstance(beta, dict) else None
    rp, sp = _num(return_pct), _num(spy_leg_pct)
    out: dict = {"method": method, "n_obs": (beta or {}).get("n_obs", 0)}

    def all_cd(why: str) -> dict:
        out.update(beta=_cd(why), up_capture=_cd(why), down_capture=_cd(why),
                   beta_adjusted_excess_pp=_cd(why), by_month=_cd(why),
                   series_beta_adjusted_pp=_cd(why))
        return out

    numeric = isinstance(bval, (int, float)) and not isinstance(bval, bool)
    if not numeric and bval != NOT_CREDIBLE:
        return all_cd(f"beta {bval}: {(beta or {}).get('why') or 'no beta'}")
    if session_dates is None and spy_close:
        session_dates = sorted(spy_close)
    # the beta window lies inside the receipt window: a period-return series read later than
    # the receipt (a --rebuild-dna on an old receipt reads today's leaderboards) is cut at its mark
    last = str((window or (None, None))[1] or "")[:10]
    if _ISO_DAY.match(last) and series:
        kept_s = [q for q in series if not (_ISO_DAY.match(str(q[0])) and str(q[0])[:10] > last)]
        if len(kept_s) < len(series):
            out["n_periods_after_the_receipt_mark_dropped"] = len(series) - len(kept_s)
            series = kept_s
    check, est = stamp_screen(series, min_month_obs=int(q["stamp_month_min_obs"]),
                              min_lag_corr=float(q["stamp_month_min_lag_corr"]),
                              gap_se=float(q["stamp_month_gap_se"]), spy_close=spy_close)
    out["stamp_check"] = check
    if check["failing_months"]:
        fm = "; ".join(f"{r['month']} same-day {r['corr_same_day']:+.2f} / lag -1 {r['corr_lag_minus_1']:+.2f}"
                       for r in check["months"] if r["month"] in check["failing_months"])
        lead = f"date stamp lag in {len(check['failing_months'])} month(s) ({fm})"
        if not est:
            return all_cd(f"{lead}; no period after the last failing month")
        b2 = beta_of(est, int(q["min_beta_obs"]))
        if not isinstance(b2.get("value"), float):
            return all_cd(f"{lead}; on the {len(est)} periods after it: beta {b2.get('value')}: {b2.get('why')}")
        bval = b2["value"]
        out["n_obs"] = b2["n_obs"]
        out["stamp_note"] = (f"{lead}: exposure estimated on {est[0][0]}..{est[-1][0]} only "
                             f"({len(est)} periods, lag 0 there); dates were not shifted")
    elif not numeric:
        return all_cd(f"beta {bval}: {(beta or {}).get('why') or 'no beta'}")
    b = float(bval)
    spans = _session_spans(est, session_dates)
    rows = [(d, float(x), float(y), sp_) for (d, x, y), sp_ in zip(est, spans)
            if _num(x) is not None and _num(y) is not None]
    yv = np.array([x for _, x, _, _ in rows])
    xv = np.array([y for _, _, y, _ in rows])
    n = len(rows)
    if n == 0 or np.std(yv) == 0:
        return all_cd("flat NAV over the whole series (all cash, never held a position, or a NAV that did "
                      "not update): exposure is undefined, not 0")
    sxx = float(np.sum((xv - xv.mean()) ** 2))
    resid = yv - (yv.mean() - b * xv.mean()) - b * xv
    se_b = math.sqrt(float(np.sum(resid ** 2)) / max(n - 2, 1) / sxx) if sxx > 0 else float("inf")
    d0, d1 = rows[0][0], rows[-1][0]
    out["beta"] = {"value": round(b, 3), "se": round(se_b, 3), "n_obs": n, "from": d0, "to": d1}
    one = [(x, y) for _, x, y, s_ in rows if s_ is None or s_ <= 1]
    out["n_multi_session_periods_excluded_from_capture"] = n - len(one)
    out["up_capture"] = _capture(one, "up", mco, float(q["max_capture_se"]))
    out["down_capture"] = _capture(one, "down", mco, float(q["max_capture_se"]))
    cb = float(np.prod(1 + yv) - 1)
    cs = float(np.prod(1 + xv) - 1)
    reasons = []
    cover = (n / sessions) if sessions else None
    if cover is not None and cover < float(q["exposure_min_cover"]):
        reasons.append(f"it covers {n} of {sessions} receipt sessions ({cover:.0%} < "
                       f"{float(q['exposure_min_cover']):.0%})")
    gap = (100 * cb - rp) if rp is not None else None
    if gap is not None and abs(gap) > float(q["exposure_max_return_gap_pp"]):
        reasons.append(f"its book return {100 * cb:+.2f}% is {gap:+.2f} pp from the receipt return {rp:+.2f}% "
                       f"(> {float(q['exposure_max_return_gap_pp']):.1f} pp)")
    rw = window or (None, None)
    out["estimation_window"] = {
        "from": d0, "to": d1, "n_periods": n, "receipt_from": rw[0], "receipt_to": rw[1],
        "receipt_sessions": sessions, "coverage": None if cover is None else round(cover, 3),
        "series_book_pct": round(100 * cb, 3), "series_spy_pct": round(100 * cs, 3),
        "return_gap_pp": None if gap is None else round(gap, 3), "comparable": not reasons,
        "why": "; ".join(reasons) or None}
    ve = float(np.var(yv - b * xv, ddof=1)) if n > 1 else float("inf")

    def se_pp(spy_frac: float) -> float:
        return 100 * math.sqrt(n * ve + (se_b * spy_frac) ** 2)

    fig = 100 * (float(np.prod(1 + yv - b * xv)) - 1)
    fse = se_pp(cs)
    out["series_beta_adjusted_pp"] = {
        "value": round(fig, 3), "se_pp": round(fse, 3), "mde_pp": round(float(q["mde_z"]) * fse, 3),
        "series_book_pct": round(100 * cb, 3), "series_spy_pct": round(100 * cs, 3),
        "from": d0, "to": d1, "n_periods": n,
        "note": "compounded over the beta window's own periods (the estimation_window)"}
    if rp is None or sp is None:
        out["beta_adjusted_excess_pp"] = _cd("the receipt row has no return or no SPY leg")
    elif reasons:
        out["beta_adjusted_excess_pp"] = _cd(
            f"not comparable: beta measured on {d0}..{d1} ({n} periods) and the receipt window is "
            f"{rw[0]}..{rw[1]} ({sessions} sessions): {'; '.join(reasons)}. Over the beta's own window "
            f"the beta-adjusted excess is {fig:+.2f} pp (SE {fse:.2f}); this beta applied to the whole "
            f"receipt window would give {rp - b * sp:+.2f} pp, a number whose beta never saw most of that window",
            window_figure_pp=round(fig, 3), window_figure_se_pp=round(fse, 3), window_from=d0, window_to=d1,
            window_n_periods=n, receipt_window_with_this_beta_pp=round(rp - b * sp, 3))
    else:
        se = se_pp(sp / 100.0)
        rf = float(q["rf_annual_assumed"])
        rfe = (1.0 - b) * rf * (sessions / 252.0) * 100 if sessions else None
        out["beta_adjusted_excess_pp"] = {
            "value": round(rp - b * sp, 3), "raw_excess_pp": round(rp - sp, 3),
            "beta_part_pp": round((b - 1.0) * sp, 3), "basis": "receipt window",
            "se_pp": round(se, 3), "mde_pp": round(float(q["mde_z"]) * se, 3),
            "rf_effect_pp": None if rfe is None else round(rfe, 3),
            "rf_note": (None if rfe is None else
                        f"rf = 0 declared; with cash at an ASSUMED {rf:.0%}/yr over {sessions} sessions, "
                        f"Jensen's alpha = this value - {rfe:+.2f} pp ((1 - beta) x rf x T)")}
    months: dict = {}
    for d, x, y, _ in rows:
        months.setdefault(str(d)[:7], []).append((x, y))
    bm = []
    for m, v in sorted(months.items()):
        mb_ = float(np.prod([1 + x for x, _ in v]) - 1)
        ms_ = float(np.prod([1 + y for _, y in v]) - 1)
        cr = float(np.prod([1 + x - b * y for x, y in v]) - 1)
        bm.append({"month": m, "n_periods": len(v), "book_pct": round(100 * mb_, 3),
                   "spy_pct": round(100 * ms_, 3), "raw_excess_pp": round(100 * (mb_ - ms_), 3),
                   "beta_adjusted_pp": round(100 * cr, 3)})
    out["by_month"] = bm
    return out


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
    """Top-1 / top-2 holdings' share of the contributions IN THE DIRECTION of the
    total (gains for a winner, losses for a loser). `share` is top / sum of the
    same-direction contributions, so it is bounded 0..1 (review F6: a share of a
    near-zero NET exploded past 700%); `share_of_net` is kept beside it."""
    vals = {k: v for k, v in contrib.items() if _num(v) is not None}
    tot = sum(vals.values())
    if not vals or abs(tot) < min_abs:
        return {"status": NOT_COMPUTABLE, "basis": basis,
                "why": "no priced contribution" if not vals else "total ~ 0: a share of nothing"}
    sgn = 1.0 if tot > 0 else -1.0
    ranked = sorted(vals.items(), key=lambda kv: -sgn * kv[1])
    gross = sum(v for v in vals.values() if sgn * v > 0)
    t1 = ranked[0]
    t2 = ranked[1] if len(ranked) > 1 and sgn * ranked[1][1] > 0 else (None, 0.0)
    out = {"status": "OK", "basis": basis, "total": round(tot, 6),
           "gross_same_direction": round(gross, 6),
           "top1": {"ticker": t1[0], "share": round(t1[1] / gross, 3) if gross else None,
                    "share_of_net": round(t1[1] / tot, 3)},
           "top2": {"tickers": [t1[0]] + ([t2[0]] if t2[0] else []),
                    "share": round((t1[1] + t2[1]) / gross, 3) if gross else None}}
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


def _one_name(e: dict, tail: dict, p: dict) -> tuple:
    """Review F6: the flag is computed only on the EXCESS basis, for a non-twin,
    when |excess| >= BOOK_DNA_ONE_NAME_MIN_EXCESS_PP and the reconstruction
    agrees with the receipt within BOOK_DNA_ONE_NAME_MAX_RECON_GAP_PP; the share
    is top-1 / same-direction contributions (0..1)."""
    if e["category"] == "twin":
        return None, "twin: not flagged"
    if tail.get("status") != "OK":
        return None, f"tail NOT_COMPUTABLE ({tail.get('why')})"
    if tail.get("basis") != "active_contribution":
        return None, f"basis {tail.get('basis')} is not the excess"
    ex = e.get("excess_pp")
    if ex is None or abs(ex) < p["one_name_min_excess_pp"]:
        return None, f"|excess| < {p['one_name_min_excess_pp']} pp: a share of noise"
    gap = abs(float(tail.get("reconstructed_excess_pp") or 0.0) - ex)
    if gap > p["one_name_max_recon_gap_pp"]:
        return None, f"reconstruction off by {gap:.2f} pp"
    sh = (tail.get("top1") or {}).get("share")
    if sh is None:
        return None, "no same-direction contribution"
    return bool(sh > p["one_name_share"]), f"top-1 {tail['top1']['ticker']} = {sh:.0%} of same-direction"


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


# ───────────────────────────── flags (claims-none, 2026-11-14) ──────────────
#
# The owner (2026-11-14): "see how we can improve the labeling and classification overall".
# The S69 fleet review had to work out by hand that hack2 was "ahead" only through a calendar
# exit to cash, that a REPLICATED pharma book did what its equal-weight version did, that five
# books never held a position, that an "abstention" book was its comparator, that the leaders
# were one bet, and that every excess sat far below its MDE. These FLAGS print that beside the
# label. A flag never raises (or lowers) a label; each one is derived from this receipt's own
# data or says CANNOT DETERMINE with the reason.

FLAG_SET, FLAG_CLEAR, FLAG_NA = "SET", "CLEAR", "N/A"
FLAG_ORDER = ("NEVER_INVESTED", "IDLE_CASH", "SAME_BET", "MDE", "ONE_MONTH", "ONE_NAME",
              "SIZING_ADDED_NOTHING", "IDENTICAL_TO_COMPARATOR", "HIGH_BETA")


def _fcd(why: str, **extra: Any) -> dict:
    return {"status": CANNOT_DETERMINE, "why": why, **extra}


def _spy_sessions(px: Prices, inception: Optional[str], last_mark: Optional[str]) -> list[str]:
    inc, lm = str(inception or "")[:10], str(last_mark or "")[:10]
    return [d for d in px.dates("SPY") if (not inc or d >= inc) and (not lm or d <= lm)]


def gross_path(e: dict, inputs: dict, sessions: list[str]) -> dict:
    """Gross exposure / equity per session from inception to the last mark, from the most
    direct source each family has; a session before the first observation is None (unknown).
    Sources: alpaca fleet = gross_over_equity at every fleet_daily read; PC-PAPER = long + |short|
    market value / equity per nav.jsonl row; night books = the weights of each recorded decision
    (cash before the first one); llm books = the frozen entry weights; otherwise the NAV-unchanged
    proxy (a period whose NAV did not move counts as idle) -- which cannot tell all cash from a
    NAV that did not update, and says so in its basis."""
    fam, acct = e["family"], e["account"]
    pts: Optional[list] = None
    basis = ""
    if fam == "alpaca_fleet":
        g = (inputs.get("fleet_gross") or {}).get(acct)
        if g:
            pts, basis = list(g), "gross_over_equity at each fleet_daily read (step until the next read)"
    elif fam == "pc_paper":
        g = inputs.get("pc_gross")
        if g:
            pts, basis = list(g), "(long + |short| market value) / equity per pc nav.jsonl row"
    elif fam in ("night_books", "night_books_twin"):
        dec = inputs.get("night_decisions")
        if isinstance(dec, dict):
            rows = dec.get(str(e.get("book_id"))) or []
            pts = [(sessions[0] if sessions else str(e.get("inception"))[:10], 0.0)] if sessions else []
            pts += [(d, sum(abs(w) for t, w in wts.items() if t not in CASH_TICKERS and w is not None))
                    for d, wts in rows]
            basis = (f"paper_book_decisions weights ({len(rows)} decision(s); cash before the first)"
                     if rows else "paper_book_decisions: no decision recorded for this book")
    elif fam.startswith("llm_portfolio"):
        w = [v for t, v in (e.get("weights") or {}).items() if t not in CASH_TICKERS and v is not None]
        if e.get("weights") is not None and sessions:
            pts, basis = [(sessions[0], float(sum(abs(x) for x in w)))], "frozen entry weights (constant)"
    if pts is None:
        ser = e.get("_series") or []
        if not ser or not sessions:
            return {"status": CANNOT_DETERMINE, "why": "no gross source and no period-return series"}
        periods, prev = [], sessions[0]
        for d, b, _ in ser:
            if _num(b) is not None:
                periods.append((prev, str(d)[:10], 0.0 if abs(float(b)) < 1e-9 else 1.0))
            prev = str(d)[:10]
        per = []
        for s in sessions:
            st = next((g for a, d, g in periods if a < s <= d), None)
            if st is None and s == sessions[0] and periods:
                st = periods[0][2]
            per.append((s, st))
        return {"status": "OK", "basis": ("NAV-unchanged proxy: a period whose NAV did not move counts as "
                                          "idle (cannot tell all cash from a NAV that did not update)"),
                "per_session": per, "proxy": True, "last_observation": ser[-1][0] if ser else None}
    pts = sorted((str(d)[:10], float(g)) for d, g in pts if g is not None)
    per, j, cur = [], 0, None
    for s in sessions:
        while j < len(pts) and pts[j][0] <= s:
            cur = pts[j][1]
            j += 1
        per.append((s, cur))
    return {"status": "OK", "basis": basis, "per_session": per, "proxy": False,
            "last_observation": pts[-1][0] if pts else None}


def idle_flags(e: dict, gp: dict, p: dict) -> tuple[dict, dict, dict]:
    """(IDLE_CASH, NEVER_INVESTED, excess-while-idle). IDLE_CASH: gross < flag_idle_gross for the
    last >= flag_idle_min_sessions sessions of the window (since = the first of them, i.e. the
    first read that saw it idle). NEVER_INVESTED: every session from inception below it. The
    excess accrued while idle compounds the book and SPY over the periods that START idle (the
    holdings over (d0, d1] are those at d0); "from cash, not from positions" when it carries more
    than flag_from_cash_share of the receipt excess, in the same direction."""
    if gp.get("status") != "OK":
        cd = _fcd(gp.get("why") or "no gross path")
        return cd, dict(cd), dict(cd)
    thr, mins = float(p["flag_idle_gross"]), int(p["flag_idle_min_sessions"])
    per = gp["per_session"]
    known = [(d, g) for d, g in per if g is not None]
    if not known:
        cd = _fcd(f"no gross observation inside the window ({gp['basis']})")
        return cd, dict(cd), dict(cd)
    base = {"basis": gp["basis"], "threshold_gross": thr, "last_observation": gp.get("last_observation")}
    run: list = []
    for d, g in reversed(per):
        if g is None or g >= thr:
            break
        run.append(d)
    run.reverse()
    if run and len(run) >= mins:
        idle = {"status": FLAG_SET, "since": run[0], "sessions": len(run), **base}
    else:
        idle = {"status": FLAG_CLEAR, "trailing_idle_sessions": len(run), **base}
    if any(g >= thr for _, g in known):
        never = {"status": FLAG_CLEAR, "max_gross": round(max(g for _, g in known), 3), **base}
    elif per[0][1] is None:
        never = _fcd(f"the gross path starts {known[0][0]}, after inception {per[0][0]}; every observed "
                     f"session is below {thr:.0%}", **base)
    elif len(per) < mins:
        never = _fcd(f"{len(per)} sessions < {mins}", **base)
    else:
        never = {"status": FLAG_SET, "sessions": len(per), **base}
        if gp.get("proxy") or "no decision recorded" in gp["basis"]:
            never["note"] = "read from a NAV that never moved / no recorded decision, not from holdings"
    # excess while idle
    ex = _num(e.get("excess_pp"))
    if never.get("status") == FLAG_SET:
        return idle, never, {"status": "OK", "idle_sessions": len(per), "excess_while_idle_pp": ex,
                             "receipt_excess_pp": ex, "from_cash": bool(ex),
                             "basis": "never invested: the whole excess is cash against SPY"}
    gross_at = dict(per)
    ser = e.get("_series") or []
    sess_sorted = [d for d, _ in per]
    proxy = bool(gp.get("proxy"))
    # a session is idle-HELD when the book carried cash from its close into the next session;
    # the window's last session holds nothing inside the window (proxy: the period itself)
    idle_days = {d for d, g in per if g is not None and g < thr and (proxy or d != sess_sorted[-1])}
    if not idle_days:
        wi = {"status": "OK", "idle_sessions": 0, "excess_while_idle_pp": 0.0, "from_cash": False}
        return idle, never, wi
    if not ser:
        return idle, never, _fcd("no period-return series to split the excess by idle periods")
    prev, pb, ps, covered = None, 1.0, 1.0, set()
    for d, b, s in ser:
        d = str(d)[:10]
        start = prev
        prev = d
        if start is None:
            continue
        g0 = gross_at.get(d) if proxy else gross_at.get(start)
        if g0 is not None and g0 < thr:
            pb *= 1 + float(b)
            ps *= 1 + float(s)
            covered |= ({x for x in sess_sorted if start < x <= d} if proxy
                        else {x for x in sess_sorted if start <= x < d})
    wi_pp = 100 * (pb - ps)
    unc = len(idle_days - covered - ({sess_sorted[0]} if proxy else set()))
    wi = {"status": "OK", "idle_sessions": len(idle_days), "idle_sessions_not_in_series": unc,
          "excess_while_idle_pp": round(wi_pp, 3), "receipt_excess_pp": ex,
          "basis": ("periods whose NAV did not move" if proxy else
                    "periods that START with gross below the threshold (holdings at the period's start)")}
    if unc > 0.2 * len(idle_days):
        return idle, never, {**wi, **_fcd(f"{unc} of {len(idle_days)} idle sessions are not in the "
                                          f"period-return series")}
    wi["from_cash"] = bool(ex is not None and ex != 0 and wi_pp * ex > 0
                           and abs(wi_pp) > float(p["flag_from_cash_share"]) * abs(ex))
    return idle, never, wi


def _per_session_excess(series: list, session_dates: list) -> tuple[np.ndarray, list]:
    spans = _session_spans(series, session_dates)
    x, sp = [], []
    for (d, b, s), k in zip(series, spans):
        if _num(b) is None or _num(s) is None:
            continue
        k = k if (k and k > 0) else 1
        x.append((float(b) - float(s)) / math.sqrt(k))
        sp.append(k)
    return np.array(x), sp


def mde_flag(e: dict, session_dates: list, p: dict) -> dict:
    """BELOW_MDE / ABOVE_MDE: |receipt excess| against MDE = mde_z x SE of the RAW excess, SE =
    sd per session x sqrt(receipt sessions) (per-session sd from the period series, each period
    scaled by sqrt(its sessions); iid sessions). The beta-adjusted excess and the MDE book_dna
    already computed for it (market_exposure) are printed beside it when they exist."""
    ex = _num(e.get("excess_pp"))
    ser = e.get("_series") or []
    n_s = e.get("sessions_graded")
    if ex is None:
        return _fcd("no excess on the receipt row")
    x, sp = _per_session_excess(ser, session_dates)
    if len(x) < int(p["flag_mde_min_obs"]):
        return _fcd(f"{len(x)} period returns < {p['flag_mde_min_obs']}", excess_pp=ex)
    sessions = int(n_s) if n_s else int(sum(sp))
    se = 100 * float(np.std(x, ddof=1)) * math.sqrt(sessions)
    mde = float(p["mde_z"]) * se
    out = {"status": "BELOW_MDE" if abs(ex) < mde else "ABOVE_MDE", "excess_pp": round(ex, 3),
           "se_pp": round(se, 3), "mde_pp": round(mde, 3), "n_periods": len(x), "sessions": sessions,
           "basis": (f"raw excess vs SPY; per-session sd from {len(x)} periods ({ser[0][0]}..{ser[-1][0]}) "
                     f"scaled to {sessions} receipt sessions; MDE = {p['mde_z']:g} x SE")}
    bx = ((e.get("market_exposure") or {}).get("beta_adjusted_excess_pp") or {})
    if isinstance(bx.get("value"), (int, float)) and _num(bx.get("mde_pp")) is not None:
        out["beta_adjusted_excess_pp"] = bx["value"]
        out["beta_adjusted_mde_pp"] = bx["mde_pp"]
    return out


def one_month_flag(e: dict, session_dates: list, p: dict) -> dict:
    """ONE_MONTH: leaving out the calendar month that contributes most in the direction of the
    excess flips its sign. Read on the period series, which must cover >= exposure_min_cover of
    the receipt sessions and agree with the receipt excess in sign."""
    ex = _num(e.get("excess_pp"))
    ser = [(str(d)[:10], float(b), float(s)) for d, b, s in e.get("_series") or []
           if _num(b) is not None and _num(s) is not None]
    if ex is None or ex == 0:
        return _fcd("no non-zero excess on the receipt row")
    if len(ser) < 3:
        return _fcd(f"{len(ser)} period returns")
    spans = [k if (k and k > 0) else 1 for k in _session_spans(ser, session_dates)]
    n_s = e.get("sessions_graded") or 0
    cov = sum(spans) / n_s if n_s else None
    if cov is not None and cov < float(p["exposure_min_cover"]):
        return _fcd(f"the series covers {sum(spans)} of {n_s} receipt sessions ({cov:.0%})")

    def excess(rows: list) -> float:
        return 100 * (float(np.prod([1 + b for _, b, _ in rows])) - float(np.prod([1 + s for _, _, s in rows])))
    full = excess(ser)
    if full * ex <= 0:
        return _fcd(f"the series' own excess {full:+.2f} pp disagrees in sign with the receipt's {ex:+.2f} pp")
    months = sorted({d[:7] for d, _, _ in ser})
    if len(months) < 2:
        return _fcd("the series spans one calendar month")
    sgn = 1.0 if full > 0 else -1.0
    loo = {m: excess([q for q in ser if q[0][:7] != m]) for m in months}
    best = min(months, key=lambda m: (sgn * loo[m], m))
    flips = sgn * loo[best] <= 0
    return {"status": FLAG_SET if flips else FLAG_CLEAR, "month": best,
            "excess_without_month_pp": round(loo[best], 3), "series_excess_pp": round(full, 3),
            "n_months": len(months)}


def one_name_flag(e: dict, p: dict) -> dict:
    """ONE_NAME: one holding carries more than flag_one_name_share of the GAIN (top-1 share of the
    same-direction active contributions, the same gates as `_one_name`)."""
    ex = _num(e.get("excess_pp"))
    if e.get("category") == "twin":
        return {"status": FLAG_NA, "why": "twin"}
    if ex is None or ex <= 0:
        return {"status": FLAG_NA, "why": "no gain to attribute (excess <= 0)"}
    t = e.get("tail") or {}
    if t.get("status") != "OK":
        return _fcd(f"tail NOT_COMPUTABLE: {t.get('why')}")
    if t.get("basis") != "active_contribution":
        return _fcd(f"tail basis is {t.get('basis')} (open positions' P&L), not the gain over SPY")
    if abs(ex) < float(p["one_name_min_excess_pp"]):
        return _fcd(f"|excess| {ex:.2f} < {p['one_name_min_excess_pp']} pp: a share of noise")
    gap = abs(float(t.get("reconstructed_excess_pp") or 0.0) - ex)
    if gap > float(p["one_name_max_recon_gap_pp"]):
        return _fcd(f"the holdings reconstruction is off the receipt by {gap:.2f} pp")
    top = t.get("top1") or {}
    sh = _num(top.get("share"))
    if sh is None:
        return _fcd("no same-direction contribution")
    return {"status": FLAG_SET if sh > float(p["flag_one_name_share"]) else FLAG_CLEAR,
            "ticker": top.get("ticker"), "share": round(sh, 3), "threshold": float(p["flag_one_name_share"])}


def _diff_se_pp(a: list, b: list, session_dates: list, sessions: Optional[int]) -> Optional[tuple]:
    db = {str(d)[:10]: float(x) for d, x, _ in b if _num(x) is not None}
    rows = [(str(d)[:10], float(x) - db[str(d)[:10]], 0.0) for d, x, _ in a
            if _num(x) is not None and str(d)[:10] in db]
    x, sp = _per_session_excess(rows, session_dates)
    if len(x) < 3:
        return None
    n = int(sessions) if sessions else int(sum(sp))
    return 100 * float(np.std(x, ddof=1)) * math.sqrt(n), len(x)


def sizing_flag(e: dict, ew: Optional[dict], px: Prices, session_dates: list, mde: dict) -> dict:
    """SIZING_ADDED_NOTHING: the equal-weight version of the same names is within one SE of the
    book. Needs FROZEN holdings (llm books). The equal-weight figure is the grader's own `ew`
    twin when one exists (SE of the book-minus-twin difference series), else a reconstruction
    from the bars at the same invested fraction (SE of the book's excess)."""
    if not str(e.get("family")).startswith("llm_portfolio") or e.get("category") == "twin":
        return _fcd("needs frozen holdings: this book's positions change over the window and the "
                    "holdings path is not replayed here")
    w = {t: v for t, v in (e.get("weights") or {}).items() if t not in CASH_TICKERS}
    if not w:
        return _fcd("no holdings")
    vals = [v for v in w.values() if v is not None]
    is_ew = bool(vals) and len(vals) == len(w) and max(vals) - min(vals) < 1e-6
    if ew is not None and _num(ew.get("return_pct")) is not None and _num(e.get("return_pct")) is not None:
        diff = float(e["return_pct"]) - float(ew["return_pct"])
        se_n = _diff_se_pp(e.get("_series") or [], ew.get("_series") or [], session_dates, e.get("sessions_graded"))
        if se_n:
            se, basis = se_n[0], f"SE of the book-minus-ew-twin difference ({se_n[1]} periods)"
        elif _num(mde.get("se_pp")) is not None:
            se, basis = float(mde["se_pp"]), "SE of the book's excess (no common twin series)"
        else:
            return _fcd("no SE: neither a common twin series nor an excess SE", diff_pp=round(diff, 3))
        src = f"ew twin {ew['account']}"
        ew_ret = float(ew["return_pct"])
        book_ret = float(e["return_pct"])
    else:
        inc, lm = e.get("inception"), e.get("last_mark")
        rets, unpriced = {}, 0.0
        for t, v in w.items():
            o, c = px.open_on(t, inc), px.close_on_or_before(t, lm)
            if v is None or not (o > 0 and c == c):
                unpriced += abs(v or 0.0)
                continue
            rets[t] = c / o - 1
        inv = sum(abs(v) for v in w.values() if v is not None)
        if not rets or (inv and unpriced / inv > 0.2):
            return _fcd(f"{unpriced / inv if inv else 1:.0%} of the weight has no entry open / exit close")
        priced = {t: w[t] for t in rets}
        book_ret = 100 * sum(priced[t] * rets[t] for t in rets)
        ew_ret = 100 * sum(priced.values()) * float(np.mean(list(rets.values())))
        diff = book_ret - ew_ret
        if _num(mde.get("se_pp")) is None:
            return _fcd("no SE for the book's excess (see MDE)", diff_pp=round(diff, 3))
        se, basis = float(mde["se_pp"]), "SE of the book's excess"
        src = "equal weight of the same priced names, reconstructed from the bars (before costs)"
    out = {"status": FLAG_SET if abs(diff) < se else FLAG_CLEAR, "book_return_pct": round(book_ret, 3),
           "ew_return_pct": round(ew_ret, 3), "diff_pp": round(diff, 3), "se_pp": round(se, 3),
           "ew_source": src, "se_basis": basis}
    if is_ew:
        out["note"] = "the book is itself equal-weight"
    return out


def holdings_hash(e: dict, inputs: dict) -> tuple[Optional[str], str]:
    """A hash of what the book holds: the decision-weights PATH for night books, the frozen entry
    weights for llm books, the holdings at the last read otherwise."""
    import hashlib
    fam = str(e.get("family"))
    if fam in ("night_books", "night_books_twin"):
        dec = inputs.get("night_decisions")
        if not isinstance(dec, dict):
            return None, "paper_book_decisions not read"
        path = [(d, sorted((t, round(v, 4)) for t, v in w.items() if v is not None))
                for d, w in dec.get(str(e.get("book_id"))) or []]
        blob, basis = json.dumps(path), f"decision-weights path ({len(path)} decisions)"
    else:
        w = e.get("weights")
        if not w:
            return None, "no holdings source"
        blob = json.dumps(sorted((t, None if v is None else round(v, 3)) for t, v in w.items()))
        basis = ("frozen entry weights" if fam.startswith("llm_portfolio") else "holdings at the last read")
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16], basis


def comparators_of(e: dict, books: list[dict], markers: list[str]) -> list[dict]:
    """The books that are this book's control: its twins (twin_of), `<name>__control`, and any
    book of the same family whose name carries a control marker (the night books' comparators
    are linked by name only)."""
    acct = e["account"]
    out = []
    for b in books:
        if b is e or b["account"] == acct:
            continue
        if b.get("twin_of") == acct or b["account"] == f"{acct}__control":
            out.append(b)
        elif b.get("family") == e.get("family") and any(m in b["account"] for m in markers) \
                and not any(m in acct for m in markers):
            out.append(b)
    return out


def identical_flag(e: dict, comps: list[dict], hashes: dict) -> dict:
    if e.get("category") in ("twin", "control"):
        return {"status": FLAG_NA, "why": f"{e.get('category')}: a comparator itself"}
    if not comps:
        return {"status": FLAG_NA, "why": "no comparator or control recorded for this book"}
    h, basis = hashes.get(e["account"], (None, "no holdings"))
    hits, unknown = [], []
    for c in comps:
        hc = hashes.get(c["account"], (None, ""))[0]
        if hc is None:
            unknown.append(c["account"])
        elif h is not None and hc == h:
            hits.append(c["account"])
    nav_same = []
    for c in comps:
        if e.get("_series") and c.get("_series"):
            _, nc, ident = _series_corr(e["_series"], c["_series"])
            if ident and nc >= 2:
                nav_same.append({"account": c["account"], "n_periods": nc})
    if h is None:
        return _fcd(f"this book's holdings are not known ({basis})", nav_identical=nav_same)
    if hits:
        return {"status": FLAG_SET, "comparators": hits, "basis": basis, "nav_identical": nav_same}
    if len(unknown) == len(comps):
        return _fcd("no comparator's holdings are known", comparators=unknown, nav_identical=nav_same)
    return {"status": FLAG_CLEAR, "n_comparators": len(comps), "basis": basis, "nav_identical": nav_same,
            "comparators_holdings_unknown": unknown}


def high_beta_flag(e: dict, p: dict) -> dict:
    b = ((e.get("market_exposure") or {}).get("beta") or {})
    v = b.get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return _fcd(f"beta {v}: {b.get('why') or 'not computed'}")
    return {"status": FLAG_SET if v > float(p["flag_high_beta"]) else FLAG_CLEAR, "beta": v,
            "se": b.get("se"), "threshold": float(p["flag_high_beta"])}


def same_bet_peers(books: list[dict], p: dict, never: Optional[set] = None) -> dict:
    """{account: {status, peers: [{account, corr, n}]}}: daily-excess (r_book - r_SPY) correlation
    >= flag_same_bet_corr on >= flag_same_bet_min_obs common period dates, among the non-twin
    books. Periods are matched on their end date (the convention of `_series_corr`).

    A NEVER_INVESTED book (`never`) is a peer only of another never-invested book: its excess is
    exactly -SPY, so every low-beta book's excess correlates with it (tsmom-overlay at 0.97 on
    2026-11-14) -- that says "under-exposed to SPY", not "the same bet as cash"."""
    never = never or set()
    thr, mo = float(p["flag_same_bet_corr"]), int(p["flag_same_bet_min_obs"])
    cols = {}
    for b in books:
        if b.get("category") == "twin":
            continue
        s = {str(d)[:10]: float(x) - float(y) for d, x, y in b.get("_series") or []
             if _num(x) is not None and _num(y) is not None}
        if len(s) >= mo:
            cols[b["account"]] = s
    out: dict = {}
    for b in books:
        if b.get("category") == "twin":
            continue
        if b["account"] not in cols:
            out[b["account"]] = _fcd(f"{len(b.get('_series') or [])} period returns < {mo}")
    if cols:
        df = pd.DataFrame(cols)
        m = df.notna().astype(float)
        nmat = m.T.dot(m)
        cm = df.corr(min_periods=mo)
        for a in cols:
            peers = []
            for c in cols:
                if c == a:
                    continue
                v = cm.at[a, c]
                if (a in never) != (c in never):
                    continue
                if v == v and v >= thr and nmat.at[a, c] >= mo:
                    peers.append({"account": c, "corr": round(float(v), 3), "n": int(nmat.at[a, c])})
            out[a] = {"status": "OK", "peers": sorted(peers, key=lambda q: (-q["corr"], q["account"])),
                      "threshold": thr, "min_obs": mo}
    return out


def attach_flags(books: list[dict], inputs: dict, px: Prices, p: dict) -> None:
    """Every book gets `flags` (FLAG_ORDER keys). Twins get them too (cheap), but only the
    non-twin books are compared for SAME_BET."""
    spy_dates = px.dates("SPY")
    idles = {}
    for e in books:
        sess = _spy_sessions(px, e.get("inception"), e.get("last_mark"))
        idles[e["account"]] = idle_flags(e, gross_path(e, inputs, sess), p)
    peers = same_bet_peers(books, p, {a for a, v in idles.items() if v[1].get("status") == FLAG_SET})
    hashes = {b["account"]: holdings_hash(b, inputs) for b in books}
    markers = list(p["flag_control_name_markers"])
    twins_by_parent: dict = {}
    for b in books:
        if b.get("twin_of"):
            twins_by_parent.setdefault(b["twin_of"], []).append(b)
    for e in books:
        idle, never, wi = idles[e["account"]]
        mde = mde_flag(e, spy_dates, p)
        ew = next((t for t in twins_by_parent.get(e["account"], []) if t.get("twin_kind") == "ew"), None)
        e["flags"] = {
            "NEVER_INVESTED": never, "IDLE_CASH": idle, "EXCESS_WHILE_IDLE": wi,
            "SAME_BET": peers.get(e["account"], {"status": FLAG_NA, "why": "twin"}),
            "MDE": mde, "ONE_MONTH": one_month_flag(e, spy_dates, p), "ONE_NAME": one_name_flag(e, p),
            "SIZING_ADDED_NOTHING": sizing_flag(e, ew, px, spy_dates, mde),
            "IDENTICAL_TO_COMPARATOR": identical_flag(e, comparators_of(e, books, markers), hashes),
            "HIGH_BETA": high_beta_flag(e, p),
            "holdings_hash": hashes.get(e["account"], (None, ""))[0],
            "rule": ("flags never raise or lower a label; each is derived from this receipt's data or "
                     "says CANNOT DETERMINE with its reason"),
        }


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
    # CH-11 fix B1: SPY's session closes, for the per-month date-stamp test and capture spans
    spy_close = ({str(d): float(v) for d, v in px.close["SPY"].dropna().items()} if px.has("SPY") else {})
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
             "start_capital": _num(r.get("start_capital")),
             "twin_of": None, "book_id": r.get("book_id"),
             "category": "twin" if fam.endswith("twin") else "strategy"}
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
            elif b.get("kind") == "control":
                # review F5: a control is evidence about the control, never a bet
                e["category"] = "control"
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
        # coverage: how much of the shortfall/excess the P&L this module can SEE explains
        # (review F3: hack4's open P&L was -$181 of a -$19,424 shortfall)
        if tail.get("status") == "OK" and excess:
            if tail.get("basis") == "unrealized_pl" and e["start_capital"]:
                seen = abs(float(tail["total"])) / abs(excess / 100.0 * e["start_capital"])
            else:
                seen = abs(float(tail["total"]) * 100.0) / abs(excess)
            tail["coverage_of_excess"] = round(seen, 3)
        e["tail"] = tail
        e["one_name_dependence"], e["one_name_why"] = _one_name(e, tail, p)
        e["concentration"] = concentration(weights, smap)
        e["beta_vs_spy"] = beta_of(series, p["min_beta_obs"])
        e["market_exposure"] = market_exposure(series, e["beta_vs_spy"], return_pct=e["return_pct"],
                                               spy_leg_pct=spy_leg, min_capture_obs=p["min_capture_obs"],
                                               sessions=sessions, window=(r.get("inception"), r.get("last_mark")),
                                               spy_close=spy_close, p=p)
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
    # frozen replications: another strategy book of the same rule that is ITSELF
    # EARLY_EVIDENCE (review F7: a positive sibling was enough before)
    for e in out:
        e["_early"] = evidence_label(
            sessions=e["sessions_graded"], excess_pp=e["excess_pp"], sub=e["subwindows"],
            fair_twin_excess_pp=None, replicated_by=None, p=p)["label"] == "EARLY_EVIDENCE"
    by_rule: dict = {}
    for e in out:
        if e.get("rule") and e["category"] == "strategy":
            by_rule.setdefault(e["rule"], []).append(e)
    for e in out:
        rep = None
        for o in by_rule.get(e.get("rule"), []):
            if o is not e and o["_early"]:
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


# ───────────────────────────── ex-ante effective bets (review F1) ───────────

def participation_ratio(corr: np.ndarray) -> float:
    """Effective number of bets of a correlation matrix: (sum lambda)^2 / sum lambda^2.
    N for N uncorrelated books, 1 for N copies of one book."""
    lam = np.clip(np.linalg.eigvalsh(corr), 0.0, None)
    return float(lam.sum() ** 2 / (lam ** 2).sum()) if (lam ** 2).sum() > 0 else float("nan")


def exante_bets(books: list[dict], px: Prices, p: dict) -> dict:
    """Price each book's FROZEN weights (constant weights, daily) over the
    `exante_sessions` SPY sessions before the EARLIEST inception among them, and
    count bets on that return correlation -- raw and SPY-residual. Works on day 1
    of a book, when a realised-series correlation is impossible (review F1: the
    realised edge needed 15 periods and 34 of 39 winners had 5-6)."""
    held = [b for b in books if b.get("tickers") and b.get("inception")]
    if len(held) < 2:
        return {"status": NOT_COMPUTABLE, "why": f"{len(held)} book(s) with holdings"}
    end = min(str(b["inception"])[:10] for b in held)
    dates = [d for d in px.dates("SPY") if d < end][-(p["exante_sessions"] + 1):]
    if len(dates) < p["min_beta_obs"] + 1:
        return {"status": NOT_COMPUTABLE, "why": f"{len(dates)} sessions of bars before {end}"}
    close = px.close.reindex(dates).ffill()
    rets = close.pct_change().iloc[1:]
    spy = rets["SPY"].to_numpy()
    cols, names, excluded = [], [], {}
    for b in held:
        w = {t: float(v) for t, v in (b.get("weights") or {}).items()
             if t not in CASH_TICKERS and _num(v) is not None and float(v) > 0}
        inv = sum(w.values())
        ok = {t: v for t, v in w.items() if t in rets.columns and rets[t].notna().mean() >= 0.9}
        if inv <= 0 or sum(ok.values()) / inv < 0.8:
            excluded[b["account"]] = f"{(sum(ok.values()) / inv if inv else 0):.0%} of the weight has the window's bars"
            continue
        wt = np.array(list(ok.values())) / sum(ok.values())
        cols.append(rets[list(ok)].fillna(0.0).to_numpy() @ wt)
        names.append(b["account"])
    if len(cols) < 2:
        return {"status": NOT_COMPUTABLE, "why": "fewer than 2 books priced over the window",
                "excluded": excluded}
    M = np.column_stack(cols)
    raw = np.corrcoef(M.T)
    vs = float(np.var(spy))
    betas = [float(np.cov(spy, M[:, i], ddof=0)[0, 1] / vs) if vs > 0 else float("nan")
             for i in range(M.shape[1])]
    R = np.column_stack([M[:, i] - M[:, i].mean() - betas[i] * (spy - spy.mean())
                         for i in range(M.shape[1])])
    res = np.corrcoef(R.T)
    lam = np.clip(np.linalg.eigvalsh(raw), 0.0, None)
    iu = np.triu_indices(len(names), 1)
    uf = _UF(len(names))
    for i, j in zip(*iu):
        if raw[i, j] >= p["corr_threshold"]:
            uf.union(i, j)
    n_corr_clusters = len({uf.find(i) for i in range(len(names))})
    return {"status": "OK", "window": [dates[1], dates[-1]], "n_sessions": len(dates) - 1,
            "construction": "frozen weights held constant, daily; names with < 90% of the "
                            "window's bars dropped, book dropped if they are > 20% of its weight",
            "n_books": len(names), "books": names, "excluded": excluded,
            "effective_bets_raw": round(participation_ratio(raw), 2),
            "effective_bets_spy_residual": round(participation_ratio(res), 2),
            "top_eigen_share_raw": round(float(lam.max() / lam.sum()), 3),
            "median_pairwise_corr_raw": round(float(np.median(raw[iu])), 3),
            "median_pairwise_corr_residual": round(float(np.median(res[iu])), 3),
            f"clusters_at_corr_{p['corr_threshold']:.2f}_raw": n_corr_clusters,
            "beta_vs_spy": {n: round(b, 2) for n, b in zip(names, betas)}}


# ───────────────────────────── losers ───────────────────────────────────────

def _identity_group(b: dict, lanes: dict, books_by: dict) -> Optional[list]:
    for st in (lanes or {}).get("identity_statements") or []:
        if b["account"] in st.get("lanes", []):
            return [books_by[a] for a in st["lanes"] if a in books_by]
    return None


def classify_loser(b: dict, p: dict, group: Optional[list] = None) -> dict:
    """LOSER_RULE_ORDER, in order (printed on the receipt as `params.loser_rule_order`).
    `selection` is a positive finding (a covered loss spread across names), never
    the fall-through; a loss the visible P&L does not cover is `not_determinable`."""
    if b.get("category") in ("twin", "control") or b["family"].endswith("twin"):
        what = "control twin" if b.get("category") != "control" else "kind=control book"
        return {"error_type": "control_artifact",
                "why": f"a {what} ({b.get('twin_of') or b['account']}): informative about the "
                       f"control, not a strategy"}
    if group and len(group) > 1 and b.get("excess_pp") is not None:
        best = max(g["excess_pp"] for g in group if g.get("excess_pp") is not None)
        common = min(best, 0.0)
        diff = b["excess_pp"] - common
        return {"error_type": "decomposed",
                "decomposition": {"group": [g["account"] for g in group],
                                  "common_shortfall_pp_selection": round(common, 3),
                                  "differential_pp_treatment_sizing": round(diff, 3)},
                "why": (f"same names as {', '.join(g['account'] for g in group if g is not b)}: "
                        f"{common:+.2f} pp shared by the group's best member is SELECTION; "
                        f"this book's further {diff:+.2f} pp is TREATMENT/SIZING")}
    ms = b.get("manager_sessions_since")
    if ms is not None and ms > p["unmanaged_sessions"]:
        return {"error_type": "unmanaged",
                "why": f"no manager run in {ms} sessions (last {str(b.get('manager_last_run'))[:19]})"}
    t = b.get("tail") or {}
    cov = t.get("coverage_of_excess") if t.get("status") == "OK" else None
    covered = cov is not None and cov >= p["loss_coverage_min"] and (t.get("total") or 0) < 0
    if covered:
        s1 = t["top1"]["share"] or 0.0
        if s1 > p["loser_sizing_share"]:
            return {"error_type": "sizing_concentration",
                    "why": f"{t['top1']['ticker']} carries {s1:.0%} of the same-direction loss "
                           f"({t['basis']}, coverage {cov:.0%})"}
    sub = b.get("subwindows") or {}
    if sub.get("status") == "OK" and (b.get("excess_pp") or 0) < 0:
        w = sub["windows"]
        gross = sum(-x["excess_pp"] for x in w if x["excess_pp"] < 0)
        worst = min(w, key=lambda x: x["excess_pp"])
        if gross > 0 and worst["excess_pp"] < 0 and -worst["excess_pp"] / gross >= p["timing_share"]:
            return {"error_type": "timing_exit",
                    "why": f"{-worst['excess_pp'] / gross:.0%} of the gross negative sub-window loss "
                           f"in {worst['from']}..{worst['to']}"}
    if covered:
        return {"error_type": "selection",
                "why": f"the visible P&L covers {cov:.0%} of the loss and no name carries > "
                       f"{p['loser_sizing_share']:.0%} of it"}
    if t.get("status") != "OK":
        c = b.get("concentration") or {}
        tw = c.get("top1_weight_of_invested") or c.get("top1_weight_of_equity") or {}
        if tw and float(tw.get("weight") or 0) >= p["loser_weight_fallback"]:
            return {"error_type": "sizing_concentration",
                    "why": (f"by WEIGHT, not by P&L share (not computable: {t.get('why')}): "
                            f"{tw['ticker']} is {float(tw['weight']):.0%} of the book now")}
    why = (f"the P&L this module can see covers {cov:.0%} of the shortfall (< "
           f"{p['loss_coverage_min']:.0%}); the loss sits in closed positions or turnover it does not read"
           if cov is not None else
           f"no holdings P&L and no full-window series ({t.get('why') or sub.get('why')})")
    return {"error_type": "not_determinable", "coverage_of_loss": cov, "why": why}


# ───────────────────────────── the receipt ──────────────────────────────────

def _public(b: dict) -> dict:
    return {k: v for k, v in b.items() if not k.startswith("_")}


def _clusters_of(books: list[dict], thr: float, p: dict) -> tuple[list[dict], list[dict]]:
    comps, edges = cluster(books, jaccard_threshold=thr, corr_threshold=p["corr_threshold"],
                           min_corr_obs=p["min_corr_obs"])
    out = []
    for idx in comps:
        mem = [books[i] for i in idx]
        ex = [m["excess_pp"] for m in mem]
        out.append({"n": len(mem), "members": [m["account"] for m in mem],
                    "families": sorted({m["family"] for m in mem}),
                    "n_with_holdings": sum(1 for m in mem if m["tickers"]),
                    "shared_basket": _basket(mem, p["basket_top"]),
                    "excess_pp_total": round(float(np.sum(ex)), 3),
                    "excess_pp_mean": round(float(np.mean(ex)), 3),
                    "excess_pp_median": round(float(np.median(ex)), 3)})
    # review F2: size, then TOTAL excess, then name -- never the ROI row order
    out.sort(key=lambda c: (-c["n"], -c["excess_pp_total"], c["members"][0]))
    for k, c in enumerate(out):
        c["cluster_id"] = k
    top = out[0]["n"] if out else 0
    for c in out:
        c["tied_for_largest"] = bool(c["n"] == top and sum(1 for x in out if x["n"] == top) > 1)
    return out, edges


def build(receipt: dict, inputs: dict, px: Prices, *, today: Optional[date] = None,
          prices_source: str = "") -> dict:
    p = params()
    today = today or date.today()
    books = book_rows(receipt, inputs, px, p, today)
    attach_flags(books, inputs, px, p)
    ahead = [b for b in books if b["excess_pp"] is not None and b["excess_pp"] > 0]
    twins = [b for b in ahead if b["category"] == "twin"]
    controls = [b for b in ahead if b["category"] == "control"]
    strat = [b for b in ahead if b["category"] == "strategy"]
    clusters, edges = _clusters_of(strat, p["jaccard_threshold"], p)
    sens, loose = {}, None
    for thr in p["jaccard_sensitivity"]:
        cs, _ = _clusters_of(strat, thr, p)
        sens[f"{thr:.2f}"] = len(cs)
        if loose is None or thr < loose[0]:
            loose = (thr, cs[0] if cs else None)
    dense = [b for b in ahead if (b["sessions_graded"] or 0) >= p["early_min_sessions"]]
    short_strat = [b for b in strat if b not in dense]
    ex = exante_bets(short_strat, px, p)
    # the most frequent names across the strategy books with holdings (review F2)
    held = [b for b in strat if b["tickers"]]
    freq: dict = {}
    for b in held:
        for t in b["tickers"]:
            freq[t] = freq.get(t, 0) + 1
    top_names = [{"ticker": t, "n_books": n, "of": len(held)}
                 for t, n in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:p["basket_top"]]]
    tilt = None
    if top_names and ex.get("status") == "OK":
        t0 = top_names[0]["ticker"]
        bs = [ex["beta_vs_spy"][b["account"]] for b in held
              if t0 in b["tickers"] and b["account"] in ex["beta_vs_spy"]]
        if bs:
            tilt = {"ticker": t0, "n_books": top_names[0]["n_books"], "of": len(held),
                    "median_exante_beta_of_its_books": round(float(np.median(bs)), 2),
                    "sector": (inputs.get("sector_map") or {}).get(t0)}
    cl_names = {a for c in clusters for a in c["members"]}
    lanes = lanes_block(receipt, books, inputs, p)
    books_by = {b["account"]: b for b in books}
    losers = sorted([b for b in books if b["excess_pp"] is not None],
                    key=lambda b: b["excess_pp"])[:p["n_losers"]]
    loser_rows = []
    for b in losers:
        row = _public(b)
        row.update(classify_loser(b, p, _identity_group(b, lanes, books_by)))
        loser_rows.append(row)
    summary = summarise(n_raw=len(ahead), twins=twins, controls=controls, strat=strat,
                        clusters=clusters, sens=sens, loose=loose, exante=ex, dense=dense,
                        short_strat=short_strat, top_names=top_names, tilt=tilt,
                        n_books=len(books), p=p)
    return {
        "schema": SCHEMA, "receipt": "book_dna", "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roi_receipt_run_id": receipt.get("run_id"),
        "roi_receipt_generated_utc": receipt.get("generated_utc"),
        "params": p, "label_ceiling": LABEL_CEILING,
        "sources": {"prices": prices_source, "sector_map": inputs.get("sector_source"),
                    "gaps": inputs.get("gaps") or {}},
        "summary": summary,
        "exante_bets": ex,
        "holdings_clusters": clusters, "cluster_edges": edges,
        "cluster_count_sensitivity": sens,
        "loosest_threshold_largest_cluster": {"jaccard": loose[0] if loose else None,
                                              "cluster": loose[1] if loose else None},
        "most_frequent_names_in_strategy_winners": top_names,
        "controls_ahead": [b["account"] for b in controls],
        "twins_ahead": {"n": len(twins),
                        "n_whose_parent_is_ahead": sum(1 for t in twins if t.get("twin_of") in cl_names),
                        "by_parent": _count_by(twins, "twin_of")},
        "lanes": lanes,
        "books": [_public(b) for b in books],
        "losers": loser_rows,
        "read_me_first": ("A count of books ahead of SPY is not a count of bets: twins re-price a "
                          "parent, controls are controls, and books holding the same names or the "
                          "same exposure are one bet (ex-ante effective bets). Every label is at "
                          "most REPLICATED; nothing here is a claim."),
    }


def _count_by(rows: list, key: str) -> dict:
    out: dict = {}
    for r in rows:
        k = str(r.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _basket_str(c: Optional[dict]) -> str:
    if not c:
        return "none"
    bs = [x["ticker"] for x in c.get("shared_basket") or []]
    return ", ".join(bs) if bs else f"{c['members'][0]} (no shared holdings)"


def summarise(*, n_raw: int, twins: list, controls: list, strat: list, clusters: list,
              sens: dict, loose: Optional[tuple], exante: dict, dense: list, short_strat: list,
              top_names: list, tilt: Optional[dict], n_books: int, p: dict) -> dict:
    k = len(clusters)
    big = clusters[0] if clusters else None
    nS = len(strat)
    exb = exante.get("effective_bets_raw") if exante.get("status") == "OK" else None
    exr = exante.get("effective_bets_spy_residual") if exante.get("status") == "OK" else None
    s = {"n_ahead_raw": n_raw, "n_ahead_twins": len(twins), "n_ahead_controls": len(controls),
         "n_ahead_strategy": nS,
         "n_ahead_non_twin": nS + len(controls),
         "n_holdings_clusters_ahead": k,
         "effective_bets_exante": exb, "effective_bets_exante_spy_residual": exr,
         "exante_window": exante.get("window"), "exante_n_books": exante.get("n_books"),
         "collapse_factor_twins_controls": round(n_raw / nS, 2) if nS else None,
         "collapse_factor_holdings_overlap": round(nS / k, 2) if k else None,
         "collapse_factor_exante": (round(len(short_strat) / exb, 2) if exb else None),
         "largest_cluster_size": big["n"] if big else 0,
         "largest_cluster_share": round(big["n"] / nS, 3) if big and nS else None,
         "largest_cluster_basket": [x["ticker"] for x in (big or {}).get("shared_basket") or []],
         "largest_cluster_tied": bool((big or {}).get("tied_for_largest")),
         "clusters_ge3": [{"n": c["n"], "basket": [x["ticker"] for x in c["shared_basket"]],
                           "excess_pp_total": c["excess_pp_total"], "members": c["members"]}
                          for c in clusters if c["n"] >= 3],
         "loosest_largest": ({"jaccard": loose[0], "n": loose[1]["n"],
                              "basket": [x["ticker"] for x in loose[1]["shared_basket"]]}
                             if loose and loose[1] else None),
         "most_frequent_names": top_names, "tilt": tilt,
         "jaccard_threshold": p["jaccard_threshold"],
         "cluster_count_sensitivity": dict(sens or {}),
         "n_ahead_dense": len(dense),
         "dense_ahead": [{"account": b["account"], "excess_pp": b["excess_pp"],
                          "sessions": b["sessions_graded"]} for b in dense],
         "evidence_density_line": (
             f"every label is OBSERVED(n) because of data density, not a verdict: only "
             f"{len(dense)} of {n_raw} books ahead of SPY {'has' if len(dense) == 1 else 'have'} "
             f">= {p['early_min_sessions']} sessions"),
         "book_dna_status": "OK"}
    s["collapse_line"] = collapse_line(s)
    s["top_line"] = top_line(s, short_strat)
    return s


def collapse_line(s: dict) -> str:
    """THE line. Never print `n_ahead` without it."""
    if s.get("book_dna_status") != "OK":
        return (f"{s.get('n_ahead_raw', '?')} ahead of SPY: collapse NOT COMPUTED "
                f"({s.get('why') or 'book_dna did not run on this receipt'}) -- "
                f"the count is NOT a count of independent bets")
    if s.get("n_ahead_raw", 0) == 0:
        return "0 ahead of SPY = 0 twins + 0 controls + 0 strategy books"
    ex = s.get("effective_bets_exante")
    exs = (f"{ex:.1f} ex-ante bets ({s.get('effective_bets_exante_spy_residual'):.1f} net of SPY; "
           f"{s.get('exante_n_books')} books priced over {s.get('exante_window')})"
           if ex is not None else "ex-ante bets NOT_COMPUTABLE")
    sh = s.get("largest_cluster_share")
    big = (f"{', '.join(s.get('largest_cluster_basket') or []) or 'no shared holdings'} "
           f"({s.get('largest_cluster_size')} books, {'n/a' if sh is None else f'{100 * sh:.0f}%'}"
           f"{'; a size tie, broken by total excess' if s.get('largest_cluster_tied') else ''})")
    line = (f"{s['n_ahead_raw']} ahead of SPY = {s['n_ahead_twins']} twins + "
            f"{s['n_ahead_controls']} controls + {s['n_ahead_strategy']} strategy books; "
            f"the strategy books = {s['n_holdings_clusters_ahead']} holdings clusters at Jaccard "
            f"{s['jaccard_threshold']:.2f}, ~ {exs}; largest holdings cluster = {big}")
    lo = s.get("loosest_largest")
    if lo:
        line += f"; at Jaccard {lo['jaccard']:.2f} the largest is {', '.join(lo['basket'][:5])} ({lo['n']} books)"
    f1, f2 = s.get("collapse_factor_twins_controls"), s.get("collapse_factor_holdings_overlap")
    line += f" [collapse: twins+controls x{f1}, holdings overlap x{f2}"
    if s.get("collapse_factor_exante"):
        line += f", ex-ante x{s['collapse_factor_exante']}"
    return line + "]"


def top_line(s: dict, short_strat: list) -> str:
    """The PAPER_ACCOUNTS.md top line (review's wording, from this receipt's numbers)."""
    if s.get("book_dna_status") != "OK":
        return collapse_line(s)
    d = s.get("dense_ahead") or []
    n_raw = s["n_ahead_raw"]
    if d:
        who = "; ".join(f"{x['account']}, {x['excess_pp']:+.2f} pp / {x['sessions']} sessions" for x in d)
        head = (f"{len(d)} book{'s' if len(d) != 1 else ''} with >= 21 sessions "
                f"{'is' if len(d) == 1 else 'are'} ahead of SPY ({who}).")
    else:
        head = "No book with >= 21 sessions is ahead of SPY."
    dn = {x["account"] for x in d}
    tw = s["n_ahead_twins"]
    ct = s["n_ahead_controls"]
    ss = [b for b in short_strat if b["account"] not in dn]
    sess = [b["sessions_graded"] for b in ss if b.get("sessions_graded") is not None]
    span = (f"{min(sess)}-{max(sess)}-session" if sess and min(sess) != max(sess)
            else f"{sess[0]}-session" if sess else "short")
    ex = s.get("effective_bets_exante")
    exs = (f" ~ {ex:.1f} ex-ante bets ({s.get('effective_bets_exante_spy_residual'):.1f} net of SPY)"
           if ex is not None else "")
    t = s.get("tilt")
    tilt = ""
    if t:
        tilt = (f", the most common name {t['ticker']} ({t['n_books']} of {t['of']} books"
                + (f", {t['sector']}" if t.get("sector") else "")
                + f"; its books' ex-ante beta ~ {t['median_exante_beta_of_its_books']:.1f})")
    return (f"{head} The other {n_raw - len(d)} \"ahead\" are {tw} control twins, {ct} controls "
            f"and {len(ss)} {span} books{exs}{tilt}. Nothing here is evidence yet.")


def refused_summary(n_ahead_raw: Any, why: str) -> dict:
    s = {"n_ahead_raw": n_ahead_raw, "n_ahead_non_twin": None, "n_ahead_strategy": None,
         "n_holdings_clusters_ahead": None, "effective_bets_exante": None,
         "largest_cluster_share": None, "largest_cluster_basket": [],
         "book_dna_status": "REFUSED", "why": why[:300]}
    s["collapse_line"] = collapse_line(s)
    s["top_line"] = s["collapse_line"]
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
        fetch_lanes: bool = True, today: Optional[date] = None,
        read_only_db: bool = False) -> tuple[dict, Path]:
    """Load, build, write. Raises on failure: the caller turns that into a REFUSED
    summary on the ROI receipt (never a silent absence)."""
    inputs = inputs if inputs is not None else load_inputs(receipt, http_get=http_get,
                                                            fetch_lanes=fetch_lanes,
                                                            read_only_db=read_only_db)
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


__all__ = ["SCHEMA", "LABEL_LADDER", "LABEL_CEILING", "ERROR_TYPES", "NOT_COMPUTABLE", "CANNOT_DETERMINE",
           "market_exposure",
           "Prices", "build", "classify_loser", "cluster", "collapse_line", "evidence_label",
           "exante_bets", "participation_ratio", "top_line",
           "jaccard", "lanes_block", "load_inputs", "params", "refused_summary", "run",
           "summarise", "tail_from_contributions", "write"]
