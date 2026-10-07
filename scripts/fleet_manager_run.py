"""THE FLEET DAILY MANAGER, one pass: read, reconcile, maintain, (maybe) trade, grade.

    python -m scripts.fleet_manager_run --pass open                 # DRY for every account
    python -m scripts.fleet_manager_run --pass open --live          # modes.json decides per account
    python -m scripts.fleet_manager_run --pass preclose --live      # stops for the day's fills, exits
    python -m scripts.fleet_manager_run --freeze                    # freeze v1 + v2 contracts, no orders
    python -m scripts.fleet_manager_run --rebaseline hack5          # accept broker truth as the record

Scheduled (Windows, windowless, `pythonw`): `AegisFleetManagerOpen` 22:00 HKT
(10:00 ET, after the open settles) and `AegisFleetManagerPreclose` 03:30 HKT
(15:30 ET). STOP file: `backend/data/optimus/paper_accounts/fleet_manager/STOP`.

`--live` is necessary and NOT sufficient: every account's `modes.json` row
says whether its MAINTENANCE (stops) and its ENTRIES/EXITS are LIVE or DRY and
which contract version is active. The owner flips those lines; this script
never does. Logic lives in `backend/services/fleet_manager.py`; this file is the
only one that reaches the venue. Credentials: `AAT_HACK<n>_KEY_ID/_SECRET_KEY`
from the execution repo's `.env`, each account its OWN pair, never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402
from backend.services import fleet_manager as FM             # noqa: E402

TERMINAL_ENV = REPO.parent / "aegis-alpha-terminal" / ".env"
FLEET_DAILY_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "paper_accounts" / "fleet_daily"
BOOKS = Path(_cfg.OPTIMUS_LEDGER_DIR) / "llm_portfolio" / "books.jsonl"
DIGEST_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "digest"
PANEL = Path(_cfg.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"
SEAL_URL = "https://seal-authority-production.up.railway.app"
#: C26: the named-gate overlay (order, config, hash) stamped on every decision row.
GATES_CFG = FM.gates_config()

#: The execution repo's frozen terms (`aegis-alpha-terminal/alpha/contract.py`
#: HORIZON_REMAP + BOOK_SIZING, read 2026-09-29), copied as DATA into each v1
#: contract so the hash covers them. v1 = "hold and manage what the Railway
#: loop left, under the loop's own declared terms".
LEGACY = {
    "hack1": {"mandate": "THEME BASKET (theme_basket brain, 39-name themes universe, shares only)",
              "expected_horizon_sessions": 21, "min_normal_hold_sessions": 5, "stop_frac": 0.10,
              "profit_target_frac": None, "n": 8, "notional_each": 0.125,
              "selection_input": "theme_basket brain inside the Railway loop (volume state)"},
    "hack2": {"mandate": "DRIFT (post_event_drift, window universe)",
              "expected_horizon_sessions": 5, "min_normal_hold_sessions": 2, "stop_frac": 0.08,
              "profit_target_frac": None, "n": 8, "notional_each": 0.125,
              "selection_input": "post_event_drift brain inside the Railway loop"},
    "hack4": {"mandate": "TRACKER PROFIT-MAX (sealed upside x consensus, k=5 x 20%)",
              "expected_horizon_sessions": 126, "min_normal_hold_sessions": 42, "stop_frac": 0.12,
              "profit_target_frac": None, "n": 5, "notional_each": 0.20,
              "selection_input": "seal authority portfolios['hack4']"},
    "hack5": {"mandate": "CONVEXITY (options only: long_call, bull_call_spread)",
              "expected_horizon_sessions": 21, "min_normal_hold_sessions": 2, "stop_frac": 0.50,
              "profit_target_frac": None, "n": 6, "notional_each": 0.03,
              "selection_input": "theme_basket + post_event_drift options ranker inside the loop"},
    "hack6": {"mandate": "TRACKER DIVERSIFIED (sealed upside x consensus, k=15 x 6.67%)",
              "expected_horizon_sessions": 42, "min_normal_hold_sessions": 21, "stop_frac": 0.10,
              "profit_target_frac": None, "n": 15, "notional_each": 1.0 / 15.0,
              "selection_input": "seal authority portfolios['hack6']"},
}

#: v2 PROPOSALS: one alpha source per account, so the errors differ (the known
#: bottleneck was ten books on one signal). Each is an EXISTING frozen book with
#: its own frozen twin, expressed at the fleet's caps -- nothing invented here.
V2 = {
    "hack1": {"kind": "frozen_book", "book_id": "5d137b013692a737", "twin_book_id": "4204177563615b9a",
              "alpha_source": "human + AI thematic curation (the owner's themes: AI power, memory/foundry, "
                              "prediction markets, nuclear/resources, biotech catalysts)",
              "why_this_account": "hack1's mandate was the owner's theme basket; this is its frozen successor"},
    "hack2": {"kind": "frozen_book", "book_id": "cb8d492bb8bf9ade", "twin_book_id": "e74c9063d451e316",
              "alpha_source": "analyst revision flow (net raises x firms, 90 days, >= 3 firms)",
              "why_this_account": "hack2 was the post-event DRIFT book: an analyst action is its nearest "
                                  "measured event family; the account is flat, so nothing is displaced"},
    "hack4": {"kind": "frozen_book", "book_id": "61fa183ee45aa10a", "twin_book_id": "5d578a72cd528f21",
              "alpha_source": "the engine's candidate funnel (PROBE shortlist) sized by 1/sigma_63 "
                              "(size-of-move / risk-parity weighting)",
              "why_this_account": "hack4 was the engine-ranked tracker book; this is the engine's current "
                                  "shortlist with the one measured skill (move size) in the sizing"},
    "hack5": {"kind": "market_control",
              "alpha_source": "market-like CONTROL: ~95% SPY, the rest cash (no selection, no view)",
              "why_this_account": "the options mandate cannot run under 'no new options'; the fleet needs a "
                                  "market-like control whose errors are the market's, so every other "
                                  "account is graded against a real executed control, not only an index"},
    "hack6": {"kind": "news_sleeve",
              "alpha_source": "world-digest typed implications through SHADOW_NEWS_v0's frozen "
                              "news_signal (d > 0 only), fixed 1% of equity per name, <= 10 names, 5 sessions",
              "why_this_account": "hack6 keeps its ten tracker names under v1 terms; the free cash carries "
                                  "a small news sleeve so news is tested at small weight"},
}

DEFAULT_MODES = {
    "_doc": ("Owner-controlled. contract: v1 (hold what the loop left, loop's own terms) or v2 (the "
             "proposal). maintenance/entries: LIVE or DRY. The script never edits this file after "
             "creating it. `--live` on the command line is also required for anything LIVE."),
    "hack1": {"contract": "v1", "maintenance": "LIVE", "entries": "DRY"},
    "hack2": {"contract": "v1", "maintenance": "LIVE", "entries": "DRY"},
    "hack3": {"skip": "key answers HTTP 401 (retired 2026-09-22); credentials are the owner's"},
    "hack4": {"contract": "v1", "maintenance": "LIVE", "entries": "DRY"},
    "hack5": {"contract": "v1", "maintenance": "DRY", "entries": "DRY",
              "not_before_utc": "2026-09-29T15:00:00Z",
              "why": "the BE 290/320 spread is closed by a separate one-shot task tonight"},
    "hack6": {"contract": "v1", "maintenance": "LIVE", "entries": "DRY"},
}


# ─────────────────────────────── io helpers ─────────────────────────────────

class _Tee:
    def __init__(self, *streams):
        self.s = [x for x in streams if x is not None]

    def write(self, t):
        for x in self.s:
            try:
                x.write(t)
                x.flush()
            except Exception:                                   # noqa: BLE001 -- a dead console
                pass
        return len(t)

    def flush(self):
        pass


def setup_log(path: Path) -> None:
    """A windowless (`pythonw`) process has sys.stdout None: everything goes to
    the log, and to the console too when there is one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a", encoding="utf-8", buffering=1)          # noqa: SIM115 -- process lifetime
    sys.stdout = _Tee(sys.__stdout__ if sys.__stdout__ else None, fh)   # type: ignore[assignment]
    sys.stderr = _Tee(sys.__stderr__ if sys.__stderr__ else None, fh)   # type: ignore[assignment]


def read_env_file(p: Path) -> dict:
    if os.getenv("AAT_TEST_MODE") == "1" or os.getenv("PYTEST_CURRENT_TEST"):
        raise SystemExit("REFUSED: under test -- this script talks to the broker")
    env = {}
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_modes() -> dict:
    p = FM.modes_path()
    if not p.exists():
        FM.atomic_write_json(p, DEFAULT_MODES)
    return json.loads(p.read_text(encoding="utf-8"))


def read_books() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not BOOKS.exists():
        return out
    for line in BOOKS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("book_id") and r.get("positions") and r["book_id"] not in out:
                out[r["book_id"]] = r
    return out


def baseline_from_fleet_daily() -> tuple[Optional[str], dict[str, dict[str, float]]]:
    """The newest read-only fleet check (GET-only, same broker) as the first record."""
    files = sorted(FLEET_DAILY_DIR.glob("fleet_*.json"))
    if not files:
        return None, {}
    d = json.loads(files[-1].read_text(encoding="utf-8"))
    st = d["stamp_utc"]
    iso = f"{st[0:4]}-{st[4:6]}-{st[6:8]}T{st[9:11]}:{st[11:13]}:{st[13:15]}Z"
    out = {}
    for a in d.get("accounts") or []:
        if a.get("status") == "ok":
            out[a["role"]] = {p["symbol"]: float(p["qty"]) for p in a.get("positions") or []}
    return iso, out


# ─────────────────────────────── sigma and screens ──────────────────────────

def panel_sigma_and_screen(symbols: list[str]) -> tuple[dict[str, float], dict[str, str], dict]:
    """sigma_63 from the bar-defect-screened local panel; names the screen cut,
    removed rows from, or holds as SUSPECT in the last 400 days are excluded."""
    import pandas as pd
    import pyarrow.parquet as pq
    from backend.services import bar_defects as BD
    syms = sorted(set(symbols) | {"SPY"})
    lo = pd.Timestamp.now() - pd.Timedelta(days=400)
    t = pq.read_table(PANEL, columns=["symbol", "date", "open", "high", "low", "close", "volume"],
                      filters=[("date", ">=", lo), ("symbol", "in", syms)]).to_pandas()
    t["date"] = pd.to_datetime(t["date"])
    clean, cuts, audit = BD.screen(t, market="SPY")
    excl: dict[str, str] = {}
    for c in (audit.get("cuts") or []):
        excl[str(c["symbol"]).split("#")[0]] = f"bar-defect screen CUT {c.get('reason')} at {c.get('first_after')}"
    for s in (audit.get("suspects") or []):
        excl.setdefault(str(s["symbol"]).split("#")[0], f"bar-defect SUSPECT level break {s.get('date')}")
    kept_counts = clean.groupby("symbol").size()
    in_counts = t.groupby("symbol").size()
    for s, n_in in in_counts.items():
        if int(kept_counts.get(s, 0)) < int(n_in):
            excl.setdefault(s, f"bar-defect screen removed {int(n_in) - int(kept_counts.get(s, 0))} non-trade rows")
    sig: dict[str, float] = {}
    moved: dict[str, float] = {}
    for s, g in clean.groupby("symbol"):
        closes = g.sort_values("date")["close"].tolist()
        v = FM.sigma_from_closes(closes)
        if v:
            sig[str(s)] = v
            if len(closes) >= 6 and closes[-6] > 0:
                moved[str(s)] = round((closes[-1] / closes[-6] - 1.0) / (v * 5 ** 0.5), 3)
    last_bar = str(t["date"].max().date()) if len(t) else None
    return sig, excl, {"panel": str(PANEL.name), "last_bar": last_bar, "symbols_asked": len(syms),
                       "symbols_found": int(t["symbol"].nunique()), "screen": BD.summary(audit),
                       "moved_5d_sigma": moved}


def sigma_pool(n_max: int = 1500) -> dict[str, float]:
    """sigma_63 for the panel's liquid names (the twin pool)."""
    import pandas as pd
    import pyarrow.parquet as pq
    lo = pd.Timestamp.now() - pd.Timedelta(days=120)
    t = pq.read_table(PANEL, columns=["symbol", "date", "close", "volume"],
                      filters=[("date", ">=", lo)]).to_pandas()
    t["dv"] = t["close"] * t["volume"]
    liq = t.groupby("symbol")["dv"].median().sort_values(ascending=False)
    keep = [s for s in liq.index[:n_max] if FM._EQUITY_TICKER.match(str(s))]
    t = t[t["symbol"].isin(keep)].sort_values(["symbol", "date"])
    out = {}
    for s, g in t.groupby("symbol"):
        v = FM.sigma_from_closes(g["close"].tolist())
        if v:
            out[str(s)] = v
    return out


def issuer_map_safe() -> tuple[dict[str, str], str]:
    try:
        from backend.services import investment_committee as IC
        m, st = IC.issuer_map()
        return m, str(st.get("error") or "ok")
    except Exception as exc:                                    # noqa: BLE001 -- named in the receipt
        return {}, f"issuer map unavailable: {type(exc).__name__}: {exc}"[:200]


def stitched_safe() -> set[str]:
    try:
        from backend.services import world_digest as WD
        return WD.stitched_symbols()
    except Exception:                                           # noqa: BLE001
        return set()


def sector_map_safe() -> tuple[dict[str, str], str]:
    """The sector map book_dna / opportunities read (newest potential_universe
    identity.sector). A failure is NAMED on the receipt; the sector gate then
    puts every name in the UNKNOWN bucket, which can only shrink more."""
    try:
        from backend.services.book_dna import load_sector_map
        m, src = load_sector_map()
        return m, src
    except Exception as exc:                                    # noqa: BLE001 -- named in the receipt
        return {}, f"REFUSED: sector map unreadable ({type(exc).__name__}: {exc})"[:200]


def newest_digest() -> tuple[Optional[dict], Optional[str]]:
    files = sorted(DIGEST_DIR.glob("world_digest_*.json"))
    files = [f for f in files if not f.name.endswith(".short.txt")]
    if not files:
        return None, None
    f = files[-1]
    return json.loads(f.read_text(encoding="utf-8")), f.name


# ─────────────────────────────── contracts ──────────────────────────────────

def v1_body(role: str, twin: dict, seal_note: str) -> dict:
    lg = LEGACY[role]
    options = role == "hack5"
    return {
        "schema": "fleet_manager_contract/1", "role": role, "version": "v1",
        "licence": FM.LICENCE, "name": f"{role} v1: hold and manage what the Railway loop left",
        "alpha_source": lg["mandate"],
        "selection": {"kind": "legacy_hold", "input": lg["selection_input"],
                      "input_status": seal_note,
                      "entries": ("NONE. The mandate fails CLOSED without its selection input (execution "
                                  "repo skim layer: 'no sealed book, no trade'); the loop is down and the "
                                  "input is not produced, so this version never buys.")},
        "legacy_terms": {k: lg[k] for k in ("expected_horizon_sessions", "min_normal_hold_sessions",
                                             "stop_frac", "profit_target_frac")},
        "exits": ("HORIZON: a position whose lot entry (from broker fills) is >= expected_horizon_sessions "
                  "weekday sessions old is sold with a DAY limit near the bid. A resting stop is the other "
                  "exit. THESIS_INVALIDATED on an empty seal is NOT applied: an empty seal is a missing "
                  "input, not a verdict on the name."),
        "options": ("options are never traded by this manager; the spread is closed by its own one-shot "
                    "task" if options else "none held"),
        "stop_rule": FM.stop_rule_block(lg["stop_frac"] if not options else FM._cfg.FLEET_MANAGER_STOP_MIN_FRAC),
        "caps": FM.caps_block(), "costs": FM.costs_block(),
        "objective": ("terminal wealth of the account vs SPY and vs the matched random twin, graded daily; "
                      "no claim of skill (PRODUCT_EXPERIMENT)"),
        "twin": twin,
        "inputs": ["broker positions, orders, fills (Alpaca paper, this account's own key)",
                   "sigma_63 from the bar-defect-screened local panel"],
    }


def v2_body(role: str, books: dict[str, dict]) -> dict:
    spec = V2[role]
    body: dict[str, Any] = {
        "schema": "fleet_manager_contract/1", "role": role, "version": "v2", "licence": FM.LICENCE,
        "status": "PROPOSED (dry-run until the owner sets modes.json contract=v2, entries=LIVE)",
        "alpha_source": spec["alpha_source"], "why_this_account": spec["why_this_account"],
        "caps": FM.caps_block(), "costs": FM.costs_block(),
        "objective": ("terminal wealth vs SPY and vs the frozen twin, graded daily; the question is whether "
                      "this alpha source's errors differ from the other accounts'; no claim of skill"),
        "legacy": ("names held when v2 becomes active and not targeted by it keep their v1 terms (stop, "
                   "horizon) and are not counted as capacity: v2 fills what remains of the gross cap"),
    }
    if spec["kind"] == "market_control":
        sym, w = FM._cfg.FLEET_MANAGER_CONTROL_SYMBOL, FM._cfg.FLEET_MANAGER_CONTROL_WEIGHT
        caps = FM.caps_block()
        caps["name_cap_overrides"] = {sym: w}
        caps["daily_turnover_frac"] = 1.0
        body["caps"] = caps
        body["selection"] = {
            "kind": "market_control", "symbol": sym, "weight": w,
            "rule": (f"hold {w:.0%} of equity in {sym}, the rest cash; enter with DAY limits near the quote "
                     "(the whole position in one session: the control's turnover budget is 100% of equity); "
                     "no rebalancing drift trades below the minimum order; no view, no selection"),
            "horizon_sessions": None}
        sr = FM.stop_rule_block(FM._cfg.FLEET_MANAGER_CONTROL_STOP_FRAC)
        sr["min_frac"] = FM._cfg.FLEET_MANAGER_CONTROL_STOP_FRAC
        sr["why"] = ("a DISASTER stop, far outside noise (~12 daily sigma on SPY): a control stopped out by "
                     "a wiggle would stop being the market")
        body["stop_rule"] = sr
        body["twin"] = {"kind": "ideal_control", "weights": {sym: w},
                        "note": "the unexecuted ideal: account minus twin = the control's execution drag"}
        body["exits"] = "none by rule (held as the benchmark); the disaster stop; a new control is a new version"
        return body
    if spec["kind"] == "frozen_book":
        b, tw = books.get(spec["book_id"]), books.get(spec["twin_book_id"])
        if not b or not tw:
            raise FM.FleetRefusal(f"{role} v2: frozen book {spec['book_id']} or twin missing from books.jsonl")
        body["selection"] = {
            "kind": "frozen_book", "book_id": spec["book_id"], "book_name": b.get("name"),
            "book_frozen_utc": b.get("frozen_utc"), "book_asof": b.get("asof"),
            "positions": [{"ticker": p["ticker"], "weight": float(p["weight"])} for p in b["positions"]],
            "rule": ("hold the book's weights, each clipped at max_name_frac (never renormalised: what is "
                     "clipped or dropped stays cash); drop bar-defect / stitched names and a second share "
                     "class of one issuer; enter with DAY limits near the quote inside the daily turnover "
                     "budget; hold to the horizon; a new book is a new version"),
            "horizon_sessions": 21,
        }
        body["twin"] = {"kind": "frozen_book_twin", "book_id": spec["twin_book_id"],
                        "weights": {p["ticker"]: float(p["weight"]) for p in tw["positions"]
                                    if p["ticker"] != "CASH"}}
        body["stop_rule"] = FM.stop_rule_block(0.12)
        body["exits"] = "horizon (21 sessions from the first v2 fill) -> cash; resting stops"
    else:
        body["selection"] = {
            "kind": "news_sleeve",
            "rule": ("world_digest.news_signal over the newest digest's typed implications (horizon 5 or "
                     "20, ticker subjects, not refused; social-only implications never reach the digest's "
                     "implication list): d_i = mean(sign x confidence). Long only: names with d_i > 0, "
                     "strongest first, excluding bar-defect / stitched names and names that already moved "
                     f"> {FM._cfg.FLEET_MANAGER_NEWS_MAX_ALREADY_MOVED_SIGMA:g} five-session sigma; "
                     f"{FM._cfg.FLEET_MANAGER_NEWS_UNIT_FRAC:.0%} of equity each, at most "
                     f"{FM._cfg.FLEET_MANAGER_NEWS_MAX_NAMES} names; held "
                     f"{FM._cfg.FLEET_MANAGER_NEWS_HOLD_SESSIONS} sessions, then exited unless re-signalled"),
            "digest_max_age_h": FM._cfg.FLEET_MANAGER_NEWS_MAX_DIGEST_AGE_H,
            "llm_authority": "none: only typed, validated fields reach this rule; no free text decides an order",
            "sources_refused": "X / Reddit / StockTwits never originate an order (SOCIAL_ONLY is refused upstream)",
        }
        body["twin"] = {"kind": "v1_matched_random_twin_plus_cash",
                        "note": "the sleeve's own random twin is drawn at entry with seed = hash(role, day)"}
        body["stop_rule"] = FM.stop_rule_block(0.10)
        body["exits"] = "5 sessions unless re-signalled; resting stops; legacy names keep v1 terms"
    return body


def seal_status(role: str) -> str:
    """What the seal authority sealed today for a tracker role (public, GET)."""
    import urllib.request
    try:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with urllib.request.urlopen(f"{SEAL_URL}/{day}.json", timeout=40) as r:   # noqa: S310
            d = json.loads(r.read())
        p = (d.get("portfolios") or {}).get(role) or {}
        uc = d.get("universe_considered")
        uc = len(uc) if isinstance(uc, (list, dict)) else uc
        return (f"seal {day}: considered {uc}, candidate_pool {p.get('candidate_pool')}, "
                f"n_selected {p.get('n_selected')} (an empty seal = no entries for this mandate)")
    except Exception as exc:                                    # noqa: BLE001
        return f"seal unreadable: {type(exc).__name__}"


# ─────────────────────────────── per account ────────────────────────────────

def run_role(role: str, *, env: dict, modes: dict, pass_: str, live_flag: bool, run_id: str,
             books: dict, issuer_of: dict, stitched: set, digest: Optional[dict], digest_name: Optional[str],
             baseline: tuple[Optional[str], dict], pool: dict, rebaseline: bool,
             sector_of: Optional[dict] = None) -> dict:
    res: dict[str, Any] = {"role": role, "pass": pass_}
    sector_of = sector_of or {}
    m = modes.get(role) or {}
    if m.get("skip"):
        res.update(status="SKIPPED", why=m["skip"])
        return res
    nb = m.get("not_before_utc")
    if nb and datetime.now(timezone.utc) < datetime.fromisoformat(nb.replace("Z", "+00:00")):
        res.update(status="SKIPPED", why=f"not before {nb}: {m.get('why', '')}")
        return res
    kid, sec = env.get(f"AAT_{role.upper()}_KEY_ID"), env.get(f"AAT_{role.upper()}_SECRET_KEY")
    if not kid or not sec:
        res.update(status="NO_CREDENTIAL")
        return res
    v = FM.Venue(kid, sec)
    try:
        acct = v.account()
    except FM.FleetRefusal as exc:
        res.update(status="ACCOUNT_UNREADABLE", why=str(exc)[:200])
        return res
    clock = v.clock()
    equity, cash = float(acct["equity"]), float(acct["cash"])
    t_read = FM._now_iso()
    positions = v.positions()
    open_orders = v.open_orders()
    broker = FM.signed_positions(positions)
    res.update(account_number=acct.get("account_number"), equity=equity, cash=cash,
               last_equity=float(acct.get("last_equity") or 0), n_positions=len(positions),
               n_open_orders=len(open_orders),
               positions=[{"symbol": p["symbol"], "qty": float(p["qty"]), "price": float(p.get("current_price") or 0),
                           "market_value": float(p.get("market_value") or 0),
                           "unrealized_plpc": float(p.get("unrealized_plpc") or 0),
                           "asset_class": p.get("asset_class")} for p in positions])
    day = str(clock.get("timestamp", ""))[:10] or date.today().isoformat()
    today = date.fromisoformat(day)
    is_open = bool(clock.get("is_open"))
    mins_to_close = None
    if clock.get("next_close"):
        nc = datetime.fromisoformat(str(clock["next_close"]).replace("Z", "+00:00"))
        mins_to_close = (nc - datetime.now(timezone.utc)).total_seconds() / 60
    market_ok = is_open and (mins_to_close or 0) >= FM._cfg.FLEET_MANAGER_MIN_MINUTES_TO_CLOSE
    res["clock"] = {"session_day_et": day, "is_open": is_open,
                    "minutes_to_close": round(mins_to_close, 1) if mins_to_close is not None else None}

    # ── reconciliation ──
    sp = FM.state_path(role)
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    if rebaseline:
        state = None
        res["rebaselined"] = True
        prev_t, prev = t_read, dict(broker)
        rec = {"status": "REBASELINED", "ok": True, "mismatches": [], "foreign_orders": [],
               "why": "owner/operator accepted broker truth as the record"}
    else:
        if state:
            prev_t, prev, src = state["t"], {k: float(q) for k, q in state["positions"].items()}, "state"
        else:
            prev_t, prev = baseline[0], baseline[1].get(role)
            src = "fleet_daily receipt (GET-only check)"
        fills_since = v.fills(after=prev_t) if prev_t else []
        orders_since = v.orders_since(prev_t) if prev_t else []
        rec = FM.reconcile(prev, fills_since, broker, orders_since)
        rec.update(source=src, since=prev_t, n_fills_since=len(fills_since))
    res["reconcile"] = rec

    # ── contracts ──
    active = m.get("contract", "v1")
    c1 = FM.load_contract(role, "v1") if FM.contract_file(role, "v1").exists() else None
    c2 = FM.load_contract(role, "v2") if FM.contract_file(role, "v2").exists() else None
    if c1 is None:
        raise FM.FleetRefusal(f"{role}: v1 contract not frozen; run --freeze first")
    contract = c2 if (active == "v2" and c2) else c1
    res["contract_active"] = {"version": contract["version"], "policy_hash": contract["policy_hash"],
                              "alpha_source": contract["alpha_source"], "frozen_utc": contract.get("frozen_utc")}
    res["contract_proposed"] = ({"version": "v2", "policy_hash": c2["policy_hash"],
                                 "alpha_source": c2["alpha_source"]} if c2 else None)

    # ── sigma / screens ──
    held_eq = [p["symbol"] for p in positions if p.get("asset_class") != "us_option"]
    tgt_syms: list[str] = []
    if c2 and c2["selection"]["kind"] == "frozen_book":
        tgt_syms = [p["ticker"] for p in c2["selection"]["positions"] if p["ticker"] != "CASH"]
    if c2 and c2["selection"]["kind"] == "market_control":
        tgt_syms = list(FM.control_targets(c2))
    news_sig: dict = {}
    digest_ok = False
    if c2 and c2["selection"]["kind"] == "news_sleeve" and digest:
        from backend.services import world_digest as WD
        imps = [i for th in (digest.get("themes") or []) for i in (th.get("implications") or [])]
        news_sig = WD.news_signal(imps)
        age_h = (datetime.now(timezone.utc) - datetime.strptime(digest["stamp"], "%Y%m%dT%H%M%SZ")
                 .replace(tzinfo=timezone.utc)).total_seconds() / 3600 if digest.get("stamp") else 999
        digest_ok = age_h <= FM._cfg.FLEET_MANAGER_NEWS_MAX_DIGEST_AGE_H
        res["digest"] = {"file": digest_name, "age_h": round(age_h, 1), "fresh": digest_ok,
                         "n_implications": len(imps), "n_ticker_signals": len(news_sig)}
        tgt_syms = [t for t, s in news_sig.items() if s["d"] > 0]
    sig, excl, panel_info = panel_sigma_and_screen(held_eq + tgt_syms)
    missing = [s for s in held_eq + tgt_syms if s not in sig]
    if missing:
        try:
            start = (date.today() - timedelta(days=130)).isoformat()
            bars = v.daily_closes(missing, start)
            for s in missing:
                x = FM.sigma_from_closes([c for _, c in sorted(bars.get(s) or [])])
                if x:
                    sig[s] = x
                    excl.setdefault(s, "not in the screened panel (sigma from Alpaca IEX bars, unscreened)")
        except FM.FleetRefusal as exc:
            panel_info["alpaca_sigma_error"] = str(exc)[:160]
    for s in stitched:
        excl.setdefault(s, "stitched ticker (stitched_tickers cut list)")
    res["sigma"] = {s: round(x, 5) for s, x in sig.items() if s in held_eq or s in tgt_syms}
    res["panel"] = panel_info

    # ── pre-close: an unfilled exit limit still holds its shares, so a stop for
    # them would be rejected and the position would sleep unprotected. Cancel our
    # own open sell limits first; the exit is retried at the next open pass.
    stale_sells = []
    if pass_ == "preclose":
        stale_sells = [o for o in open_orders if str(o.get("client_order_id") or "").startswith(FM.COID_PREFIX)
                       and o.get("type") == "limit" and o.get("side") in ("sell", "buy")]
    maint_orders = [o for o in open_orders if o not in stale_sells]
    # ── maintenance ──
    maint, flags, stop_table = FM.plan_maintenance(role, positions, maint_orders, sig, contract, day, today)
    maint = [FM.Action(role, "cancel", o["symbol"], 0, "", "cancel", protective=True,
                       cancel_order_id=o.get("id"),
                       reason=("pre-close: unfilled exit limit released so the position can be re-protected; "
                               "the exit is retried next open") if o.get("side") == "sell" else
                              ("pre-close: unfilled ENTRY limit cancelled so nothing can fill after the last "
                               "protection pass; the entry is retried next open"),
                       coid=f"cancel:{o.get('id')}")
             for o in stale_sells] + maint
    res["stop_table"] = stop_table
    res["flags"] = flags

    # ── entry dates, horizon exits (legacy) ──
    all_fills = v.fills(max_pages=10) if held_eq else []
    entry, entry_how = {}, {}
    for s in held_eq:
        fs = [f for f in all_fills if f.get("symbol") == s]
        e, how = FM.lot_entry_date(broker.get(s, 0.0), fs)
        entry[s], entry_how[s] = e, how
    res["lot_entry"] = {s: {"date": str(e) if e else None, "how": entry_how[s],
                            "sessions_held": FM.sessions_between(e, today) if e else None}
                        for s, e in entry.items()}
    v2_names = set((state or {}).get("v2_names") or [])
    news_names = dict((state or {}).get("news_entries") or {})

    # ── targets (active or proposed v2) ──
    held_issuers = {issuer_of.get(s): s for s in held_eq if issuer_of.get(s)}
    def excl_for(targets_from: list[str]) -> dict[str, str]:
        e = dict(excl)
        for t in targets_from:
            iss = issuer_of.get(t)
            if iss and iss in held_issuers and held_issuers[iss] != t:
                e[t] = f"issuer {iss} already held as {held_issuers[iss]}"
        return e
    v2_plan: list[FM.Action] = []
    v2_drops: list[dict] = []
    if c2:
        sel = c2["selection"]
        if sel["kind"] == "market_control":
            targets, v2_drops = FM.control_targets(c2), []
        elif sel["kind"] == "frozen_book":
            started = (state or {}).get("v2_started")
            over = bool(started and FM.sessions_between(date.fromisoformat(started), today) >= sel["horizon_sessions"])
            targets, v2_drops = ({}, [{"why": "v2 horizon reached: exit to cash"}]) if over else FM.book_targets(
                sel["positions"], max_name=c2["caps"]["max_name_frac"], excluded=excl_for(tgt_syms),
                issuer_of=issuer_of)
        else:
            moved = dict(panel_info.get("moved_5d_sigma") or {})
            if digest_ok:
                targets, v2_drops = FM.news_targets(
                    news_sig, unit=FM._cfg.FLEET_MANAGER_NEWS_UNIT_FRAC,
                    max_names=FM._cfg.FLEET_MANAGER_NEWS_MAX_NAMES, excluded=excl_for(tgt_syms),
                    already_moved=moved)
            else:
                targets, v2_drops = {}, [{"why": "no fresh digest: the sleeve takes no new names"}]
            for s, d0 in news_names.items():     # still inside the hold window
                if FM.sessions_between(date.fromisoformat(d0), today) < FM._cfg.FLEET_MANAGER_NEWS_HOLD_SESSIONS:
                    targets.setdefault(s, FM._cfg.FLEET_MANAGER_NEWS_UNIT_FRAC)
        # LEGACY = every name held before this version bought anything. It is never sold to make room
        # and never topped up: it exits by its own declared horizon and its resting stop (owner, 09-29).
        legacy = {s for s in held_eq if s not in v2_names and s not in news_names}
        prices = {p["symbol"]: float(p.get("current_price") or 0) for p in positions}
        need = [t for t in targets if t not in prices]
        if need:
            try:
                prices.update(v.last_trades(need))
            except FM.FleetRefusal as exc:
                res["price_error"] = str(exc)[:160]
        pending: dict[str, float] = {}
        for o in open_orders:
            if o.get("type") in FM.STOP_TYPES:
                continue
            q = float(o.get("qty") or 0) - float(o.get("filled_qty") or 0)
            pending[o["symbol"]] = pending.get(o["symbol"], 0.0) + (q if o.get("side") == "buy" else -q)
        v2_plan = FM.plan_rebalance(role, targets, equity=equity, held=broker, prices=prices,
                                    legacy=legacy, pending=pending, contract=c2, day=day)
        for a_ in v2_plan:
            a_.inputs["contract_version"] = "v2"
        res["v2_targets"] = {"n": len(targets), "gross_frac": round(sum(targets.values()), 4),
                             "legacy_names": sorted(legacy), "drops": v2_drops}
    horizon = FM.plan_horizon_exits(role, positions, entry, c1, set(held_eq) if contract is c1 else
                                    {s for s in held_eq if s not in v2_names}, today, day)

    # ── which actions may be live ──
    maint_live = live_flag and m.get("maintenance") == "LIVE"
    entries_live = live_flag and m.get("entries") == "LIVE"
    acts: list[tuple[FM.Action, str]] = []           # (action, mode)
    for a in maint:
        acts.append((a, "LIVE" if maint_live else "DRY"))
    for a in horizon:
        acts.append((a, "LIVE" if entries_live else "DRY"))
    active_v2 = contract is c2 and c2 is not None
    if pass_ == "open":
        for a in v2_plan:
            acts.append((a, ("LIVE" if (entries_live and active_v2) else "DRY")))
    elif v2_plan:
        res["v2_plan_note"] = "pre-close pass: no new entries (maintenance and exits only)"

    # quotes for every limit order
    lim_syms = sorted({a.symbol for a, _ in acts if a.order_type == "limit" and not a.refused})
    quotes, lasts = {}, {}
    if lim_syms:
        try:
            quotes = v.quotes(lim_syms)
            lasts = v.last_trades(lim_syms)
        except FM.FleetRefusal as exc:
            res["quote_error"] = str(exc)[:160]
    for a, _ in acts:
        if a.order_type == "limit" and not a.refused:
            lp, how = FM.limit_for(a.side, quotes.get(a.symbol), lasts.get(a.symbol) or a.price_ref)
            if lp is None:
                a.refused = f"no price to set a limit: {how}"
            else:
                a.limit_price = lp
                a.inputs["limit_basis"] = how
                a.inputs["quote"] = quotes.get(a.symbol)

    # a sell must first release shares its resting stops hold, then re-protect the remainder
    expanded: list[tuple[FM.Action, str]] = []
    for a, mode in acts:
        if a.side == "sell" and a.order_type == "limit" and not a.refused:
            st = FM.stops_for(a.symbol, open_orders)
            for o in st:
                expanded.append((FM.Action(role, "cancel", a.symbol, 0, "", "cancel", protective=True,
                                           cancel_order_id=o.get("id"), price_ref=a.price_ref,
                                           reason=f"release shares for the {a.kind} of {a.symbol}",
                                           coid=f"cancel:{o.get('id')}"), mode))
            expanded.append((a, mode))
            rem = int(broker.get(a.symbol, 0.0)) - a.qty
            if rem > 0:
                frac, how = FM.contract_stop_frac(contract, sig.get(a.symbol))
                old = max([float(o.get("stop_price") or 0) for o in st] or [0.0])
                sp_ = max(old, FM.stop_price_for(a.price_ref, frac))
                expanded.append((FM.Action(role, "stop_new", a.symbol, rem, "sell", "stop", "gtc",
                                           stop_price=sp_, price_ref=a.price_ref, protective=True,
                                           reason=f"re-protect the {rem} left after the sell ({how})",
                                           coid=FM.client_order_id(role, day, "stoprem", a.symbol,
                                                                   contract["policy_hash"], f"{rem}"),
                                           inputs={"replaces_stop": old} if old > 0 else {}), mode))
        else:
            expanded.append((a, mode))
    acts = expanded

    # ── the named gates, in order (C26): lease -> shape -> risk; every verdict is traced ──
    order_rank = {"cancel": 0, "exit": 1, "sell": 1, "stop_new": 2, "stop_renew": 2, "buy": 3}
    acts.sort(key=lambda am: order_rank.get(am[0].kind, 9))
    used = sum(float(r.get("notional") or 0) for r in FM.read_jsonl(FM.decisions_path())
               if r.get("role") == role and r.get("session") == day and r.get("mode") == "LIVE"
               and r.get("row") == "decision" and not r.get("protective") and not r.get("refused")
               and r.get("kind") in ("buy", "sell"))
    stopped_out: Optional[dict] = {}
    try:
        since = (today - timedelta(days=int(_cfg.FLEET_GATE_COOLDOWN_LOOKBACK_DAYS))).isoformat() + "T00:00:00Z"
        for o in v.stop_fills_since(since):
            d_ = str(o.get("filled_at"))[:10]
            stopped_out[o["symbol"]] = max(stopped_out.get(o["symbol"], d_), d_)
    except FM.FleetRefusal as exc:
        stopped_out = None
        res["stop_history_error"] = str(exc)[:160]
    res["stopped_out_recent"] = stopped_out
    gctx = FM.GateCtx(equity=equity, cash=cash, held=broker,
                      mv={p["symbol"]: abs(float(p.get("market_value") or 0)) for p in positions},
                      gross=sum(abs(float(p.get("market_value") or 0)) for p in positions),
                      contract=contract, today=today, stop_file_present=FM.stop_file().exists(),
                      credential_ok=True, reconciliation_ok=bool(rec.get("ok")),
                      reconciliation_status=str(rec.get("status")), market_ok=market_ok,
                      turnover_left=contract["caps"]["daily_turnover_frac"] * equity - used,
                      stopped_out=stopped_out, sector_of=sector_of)
    traces: dict[int, list[dict]] = {}
    for a, mode in acts:
        traces[id(a)] = FM.run_gates(a, gctx, mode=mode)
    res["gate_summary"] = FM.gate_summary(traces.values())
    res["sector_gross"] = {k: round(v_, 2) for k, v_ in sorted(gctx.sector_mv.items(), key=lambda kv: -kv[1])}

    # ── worst case ──
    new_frac = {}
    for a, _ in acts:
        if a.side == "buy":
            new_frac[a.symbol] = FM.contract_stop_frac(contract, sig.get(a.symbol))[0]
    res["worst_case_now"] = FM.worst_case(positions, open_orders, [], equity, {})
    res["worst_case_after_plan"] = FM.worst_case(positions, open_orders, [a for a, _ in acts], equity, new_frac)
    lg = LEGACY.get(role, {})
    res["worst_case_formula_v1"] = FM.formula_worst_case(lg.get("n", 0), lg.get("notional_each", 0.0),
                                                         lg.get("stop_frac", 0.0), equity)
    if c2:
        if c2["selection"]["kind"] == "market_control":
            n2, avg = 1, float(c2["selection"]["weight"])
        elif c2["selection"]["kind"] == "frozen_book":
            ws = [min(float(p["weight"]), c2["caps"]["max_name_frac"]) for p in c2["selection"]["positions"]
                  if p["ticker"] != "CASH"]
            n2, avg = len(ws), (sum(ws) / len(ws) if ws else 0.0)
        else:
            n2, avg = FM._cfg.FLEET_MANAGER_NEWS_MAX_NAMES, FM._cfg.FLEET_MANAGER_NEWS_UNIT_FRAC
        res["worst_case_formula_v2"] = FM.formula_worst_case(n2, avg, c2["stop_rule"]["max_frac"], equity)

    # ── the worst case in dollars is PRINTED before the first order (CLAUDE.md protocol 4) ──
    n_live = sum(1 for a, m_ in acts if m_ == "LIVE" and not a.refused)
    wn_, wa_ = res["worst_case_now"], res["worst_case_after_plan"]
    print(f"[{role}] BEFORE ORDERS: {n_live} live order(s); worst case now ${wn_['worst_usd']:,.0f} "
          f"({wn_['worst_pct_equity']}%), gross/equity {wn_['gross_over_equity']}; after plan "
          f"${wa_['worst_usd']:,.0f} ({wa_['worst_pct_equity']}%), gross/equity {wa_['gross_over_equity']}")
    res["worst_case_printed_before_orders_utc"] = FM._now_iso()

    # ── decisions BEFORE orders, then orders ──
    out_rows = []
    for a, mode in acts:
        row = {"row": "decision", "run_id": run_id, "t": FM._now_iso(), "session": day, "pass": pass_,
               "role": role,
               "contract_version": "v2" if a.inputs.get("contract_version") == "v2" else contract["version"],
               "policy_hash": (c2["policy_hash"] if (a.inputs.get("contract_version") == "v2" and c2)
                               else contract["policy_hash"]),
               "kind": a.kind, "symbol": a.symbol, "side": a.side, "qty": a.qty, "type": a.order_type,
               "tif": a.tif, "limit_price": a.limit_price, "stop_price": a.stop_price,
               "price_at_decision": a.price_ref, "notional": round(a.notional, 2), "protective": a.protective,
               "reason": a.reason, "inputs": a.inputs, "coid": a.coid, "cancel_order_id": a.cancel_order_id,
               "mode": mode if not a.refused else "REFUSED", "refused": a.refused,
               "licence": FM.LICENCE, "story_id": FM.story_id(role, day, pass_, a.coid),
               "gates": traces.get(id(a), []), "gates_hash": GATES_CFG["hash"]}
        FM.append_jsonl(FM.decisions_path(), row)
        out = {"kind": a.kind, "symbol": a.symbol, "side": a.side, "qty": a.qty, "type": a.order_type,
               "limit": a.limit_price, "stop": a.stop_price, "mode": row["mode"], "refused": a.refused,
               "reason": a.reason, "coid": a.coid, "story_id": row["story_id"], "gates": row["gates"]}
        if mode == "LIVE" and not a.refused:
            if FM.stop_file().exists():
                out["outcome"] = "STOP file present: not sent"
            elif a.kind == "cancel":
                stc = v.cancel(a.cancel_order_id)
                term = FM.wait_terminal(v, a.cancel_order_id) if stc in (200, 204) else f"http {stc}"
                out["outcome"] = f"cancel http {stc}, {term}"
            else:
                so = FM.submit_once(v, a)
                out["outcome"], out["order_id"] = so["outcome"], so.get("order_id")
            FM.append_jsonl(FM.decisions_path(), {"row": "outcome", "run_id": run_id, "t": FM._now_iso(),
                                                  "role": role, "coid": a.coid, "outcome": out.get("outcome"),
                                                  "order_id": out.get("order_id")})
            if a.side == "buy" and ("submitted" in str(out.get("outcome"))
                                    or "ALREADY SUBMITTED" in str(out.get("outcome"))):
                v2_names.add(a.symbol)
                if c2 and c2["selection"]["kind"] == "news_sleeve":
                    news_names.setdefault(a.symbol, day)
        out_rows.append(out)
    res["actions"] = out_rows

    # ── a stop for the full quantity with each entry: wait for the entry limits, then
    # protect whatever filled in THIS run (the pre-close pass protects later fills and
    # cancels what never filled, so nothing sleeps unprotected) ──
    live_buys = [o for o in out_rows if o.get("side") == "buy" and o.get("mode") == "LIVE"
                 and o.get("order_id") and "submitted" in str(o.get("outcome"))]
    if live_buys and not FM.stop_file().exists():
        for o in live_buys:
            o["entry_status"] = FM.wait_terminal(v, o["order_id"], timeout_s=20.0)
            try:
                od = v.order(o["order_id"])
                o["filled_qty"], o["filled_avg_price"] = od.get("filled_qty"), od.get("filled_avg_price")
            except FM.FleetRefusal:
                pass
        pos_after, oo_after = v.positions(), v.open_orders()
        prot, pflags, _ = FM.plan_maintenance(role, pos_after, oo_after, sig, contract, day, today)
        res["entry_protection"] = []
        held_after = FM.signed_positions(pos_after)
        pctx = FM.GateCtx(equity=equity, cash=cash, held=held_after, mv={}, gross=0.0, contract=contract,
                          today=today, stop_file_present=FM.stop_file().exists(),
                          reconciliation_ok=bool(rec.get("ok")), reconciliation_status=str(rec.get("status")),
                          market_ok=market_ok, stopped_out=stopped_out, sector_of=sector_of)
        for a in prot:
            if a.kind != "stop_new":
                continue
            want = "LIVE" if (entries_live or maint_live) else "DRY"
            ptrace = FM.run_gates(a, pctx, mode=want)
            ok_live = want == "LIVE" and not a.refused
            mode = "LIVE" if ok_live else "REFUSED"
            a.refused = a.refused or (None if ok_live else "not live: this account's modes are DRY")
            FM.append_jsonl(FM.decisions_path(), {
                "row": "decision", "run_id": run_id, "t": FM._now_iso(), "session": day, "pass": pass_,
                "role": role, "contract_version": contract["version"], "policy_hash": contract["policy_hash"],
                "kind": a.kind, "symbol": a.symbol, "side": a.side, "qty": a.qty, "type": a.order_type,
                "tif": a.tif, "limit_price": None, "stop_price": a.stop_price, "price_at_decision": a.price_ref,
                "notional": round(a.notional, 2), "protective": True,
                "reason": "ENTRY PROTECTION: " + a.reason, "inputs": a.inputs, "coid": a.coid,
                "cancel_order_id": None, "mode": mode, "refused": a.refused, "licence": FM.LICENCE,
                "story_id": FM.story_id(role, day, pass_, a.coid), "gates": ptrace,
                "gates_hash": GATES_CFG["hash"]})
            outp = {"kind": a.kind, "symbol": a.symbol, "side": "sell", "qty": a.qty, "type": "stop",
                    "stop": a.stop_price, "mode": mode, "refused": a.refused, "coid": a.coid,
                    "reason": "entry protection", "story_id": FM.story_id(role, day, pass_, a.coid),
                    "gates": ptrace}
            if mode == "LIVE" and not FM.stop_file().exists():
                so = FM.submit_once(v, a)
                outp["outcome"], outp["order_id"], outp["coid"] = so["outcome"], so.get("order_id"), a.coid
                FM.append_jsonl(FM.decisions_path(), {"row": "outcome", "run_id": run_id, "t": FM._now_iso(),
                                                      "role": role, "coid": a.coid, "outcome": so["outcome"],
                                                      "order_id": so.get("order_id")})
            res["entry_protection"].append(outp)
        res["entry_protection_flags"] = pflags

    # ── the tight-stop counterfactual (owner's question, 2026-09-29): never changes a stop ──
    try:
        res["stop_counterfactual"] = stop_counterfactual_step(role, v, stop_table, sig, c1, day)
    except Exception as exc:                                    # noqa: BLE001 -- evidence never blocks
        res["stop_counterfactual"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}

    # ── the record for the next reconciliation (broker truth, read twice) ──
    pos2 = FM.signed_positions(v.positions())
    t2 = FM._now_iso()
    pos3 = FM.signed_positions(v.positions())
    if pos2 == pos3 and (rec.get("ok") or rebaseline):
        st_new = {"t": t2, "positions": pos3, "run_id": run_id, "contract": contract["version"],
                  "policy_hash": contract["policy_hash"], "v2_names": sorted(v2_names),
                  "news_entries": news_names,
                  "v2_started": (state or {}).get("v2_started") or (day if v2_names and active_v2 else None)}
        FM.atomic_write_json(sp, st_new)
        res["state_written"] = t2
    else:
        res["state_written"] = None
        res["state_note"] = ("positions moved between two reads, or reconciliation failed: the previous "
                             "record is kept so the mismatch stays visible")

    # ── the daily grade (open pass, previous completed session) ──
    if pass_ == "open":
        try:
            res["grade"] = grade_role(role, v, contract, day, is_open, fallback_twin=c1.get("twin"),
                                      c1=c1, v2_started=((state or {}).get("v2_started")
                                                         or (day if v2_names and active_v2 else None)))
        except Exception as exc:                                # noqa: BLE001 -- a grade never blocks
            res["grade"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    res["status"] = "ok"
    return res


def graded_contract(active: dict, c1: Optional[dict], v2_started: Optional[str], session: str) -> dict:
    """The contract IN FORCE on the graded session: v2 only from the session its first
    order went out; before that the account held v1 positions (2026-09-30: hack5's
    09-28 options loss was first stamped with the v2 control's hash)."""
    if active.get("version") == "v2" and c1 is not None and not (v2_started and session >= v2_started):
        return c1
    return active


CF_DIR = FM.root() / "stop_counterfactual"
#: A resting stop this close (in daily sigma) is registered for the counterfactual.
CF_MAX_SIGMA = 1.25


def stop_counterfactual_step(role: str, v: FM.Venue, stop_table: list[dict], sig: dict, c1: dict,
                             day: str) -> dict:
    """Register (write-once) each position whose resting stop is within CF_MAX_SIGMA
    daily sigma; then, per completed session after registration, append what the
    tight stop, a 3-sigma stop and holding would each have done. Changes no order."""
    reg_p = CF_DIR / "registry.json"
    log_p = CF_DIR / "daily.jsonl"
    reg = json.loads(reg_p.read_text(encoding="utf-8")) if reg_p.exists() else {"registrations": []}
    have = {(r["role"], r["symbol"]) for r in reg["registrations"]}
    new = []
    for row in stop_table:
        ds = [x for x in row["resting"] if x.get("distance_sigma") is not None]
        if not ds or not row.get("price"):
            continue
        tight = min(ds, key=lambda x: float(x["stop_price"]))
        if (role, row["symbol"]) in have or float(tight["distance_sigma"]) > CF_MAX_SIGMA:
            continue
        s_ = row.get("sigma_d")
        frac, how = FM.contract_stop_frac(c1, s_)
        wide = FM.stop_price_for(row["price"], frac)
        r = {"role": role, "symbol": row["symbol"], "qty": row["qty"], "p0": row["price"],
             "registered_session": day, "registered_utc": FM._now_iso(), "sigma_d": s_,
             "tight_stop": float(tight["stop_price"]), "tight_stop_sigma": tight["distance_sigma"],
             "tight_stop_coid": tight.get("client_order_id"),
             "wide_stop": wide, "wide_stop_sigma": round(frac / s_, 2) if s_ else None, "wide_how": how,
             "rule": ("forward-only: sessions strictly after the registered session; the tight stop is the "
                      "one resting at the broker and is NOT changed by this record")}
        reg["registrations"].append(r)
        new.append(r["symbol"])
    if new:
        FM.atomic_write_json(reg_p, reg)
    mine = [r for r in reg["registrations"] if r["role"] == role]
    if not mine:
        return {"registered_now": new, "rows_written": []}
    done = {(r["symbol"], r["asof_session"]) for r in FM.read_jsonl(log_p) if r.get("role") == role}
    start = min(r["registered_session"] for r in mine)
    bars = v.daily_bars(sorted({r["symbol"] for r in mine}), start)
    written = []
    intraday: dict = {}
    reg_days = {r["registered_session"] for r in mine if r["registered_session"] < day}
    for rd in sorted(reg_days):
        syms = sorted({r["symbol"] for r in mine if r["registered_session"] == rd})
        t0 = min(r["registered_utc"] for r in mine if r["registered_session"] == rd)
        end = (date.fromisoformat(rd) + timedelta(days=1)).isoformat() + "T08:00:00Z"
        for s_, xs in v.intraday_bars(syms, t0.replace("+00:00", "Z"), end).items():
            intraday[(rd, s_)] = xs
    for r in mine:
        bs = [b for b in bars.get(r["symbol"]) or [] if b["d"] < day]      # completed sessions only
        if not bs:
            continue
        asof = max(b["d"] for b in bs)
        if asof < r["registered_session"] or (r["symbol"], asof) in done:
            continue
        rdb = FM.partial_bar([b for b in intraday.get((r["registered_session"], r["symbol"])) or []
                              if b["t"] >= r["registered_utc"].replace("+00:00", "Z")], r["registered_session"])
        bt = None
        if r.get("tight_stop_coid"):
            try:
                o = v.order_by_coid(r["tight_stop_coid"])
                bt = ({"status": o.get("status"), "filled_at": o.get("filled_at"),
                       "filled_avg_price": o.get("filled_avg_price"), "filled_qty": o.get("filled_qty")}
                      if o else {"status": "not found"})
            except FM.FleetRefusal as exc:
                bt = {"error": str(exc)[:120]}
        row = FM.cf_stop_row(r, bs, asof, reg_day_bar=rdb, broker_tight=bt)
        FM.append_jsonl(log_p, row)
        written.append({"symbol": r["symbol"], "asof": asof, "tight_minus_hold_usd": row["tight_minus_hold_usd"],
                        "wide_minus_hold_usd": row["wide_minus_hold_usd"]})
    return {"registered_now": new, "registered_total": [r["symbol"] for r in mine], "rows_written": written}


def grade_role(role: str, v: FM.Venue, contract: dict, day: str, is_open: bool,
               fallback_twin: Optional[dict] = None, c1: Optional[dict] = None,
               v2_started: Optional[str] = None) -> dict:
    ph = v.portfolio_history()
    ts, eq = ph.get("timestamp") or [], ph.get("equity") or []
    # a 1D point is stamped 00:00 UTC = 20:00 ET OF THE SESSION it closes (measured
    # 2026-09-29: the 09-26T00:00Z point is Friday 09-25's close), so date it in ET
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    pts = [(datetime.fromtimestamp(t, tz=timezone.utc).astimezone(ny).date().isoformat(), float(e))
           for t, e in zip(ts, eq) if e is not None]
    # while the session is open, today's point is partial: grade the last completed one
    pts = [p for p in pts if p[0] < day] if is_open else pts
    pts = [p for p in pts if p[1] > 0]
    if len(pts) < 2:
        return {"status": "TOO_FEW_POINTS", "n": len(pts)}
    (d0, e0), (d1, e1) = pts[-2], pts[-1]
    contract = graded_contract(contract, c1, v2_started, d1)
    have = {(r.get("role"), r.get("session")) for r in FM.read_jsonl(FM.grades_path())}
    if (role, d1) in have:
        return {"status": "ALREADY_GRADED", "session": d1}
    tw = (contract.get("twin") or {}).get("weights") or (fallback_twin or {}).get("weights") or {}
    syms = sorted(set(tw) | {"SPY"})
    start = (date.fromisoformat(d0) - timedelta(days=7)).isoformat()
    bars = v.daily_closes(syms, start)
    def r_of(s: str) -> Optional[float]:
        b = dict(bars.get(s) or [])
        prev = [d for d in sorted(b) if d <= d0]
        if d1 not in b or not prev or b[prev[-1]] <= 0:
            return None
        return b[d1] / b[prev[-1]] - 1.0
    twin_r, share = FM.weighted_return(tw, {s: r_of(s) for s in tw}) if tw else (None, 0.0)
    row = FM.grade_row(role, d1, account_ret=e1 / e0 - 1.0, spy_ret=r_of("SPY"), twin_ret=twin_r,
                       twin_priced_share=share, contract=contract)
    row["equity_prev"], row["equity"], row["prev_session"] = e0, e1, d0
    row["alpha_source"] = contract.get("alpha_source")
    FM.append_jsonl(FM.grades_path(), row)
    return row


# ─────────────────────────────── freeze ─────────────────────────────────────

def freeze_all(env: dict, roles: list[str], books: dict) -> dict:
    out = {}
    pool = None
    for role in roles:
        if role not in LEGACY:
            continue
        if not FM.contract_file(role, "v1").exists():
            twin: dict[str, Any] = {"kind": "matched_random_twin", "weights": {}}
            kid, sec = env.get(f"AAT_{role.upper()}_KEY_ID"), env.get(f"AAT_{role.upper()}_SECRET_KEY")
            if kid and sec:
                try:
                    v = FM.Venue(kid, sec)
                    acct = v.account()
                    pos = [p for p in v.positions() if p.get("asset_class") != "us_option"]
                    eqv = float(acct["equity"])
                    held_w = {p["symbol"]: float(p["market_value"]) / eqv for p in pos}
                    if held_w:
                        pool = pool if pool is not None else sigma_pool()
                        sig, _, _ = panel_sigma_and_screen(list(held_w))
                        seed = int(FM._sha(role, "v1-twin", n=8), 16)
                        twin = {"kind": "matched_random_twin", "seed": seed,
                                "rule": "each held name -> a random liquid panel name in the same sigma_63 "
                                        "decile, weight copied (fraction of equity at freeze)",
                                "held_at_freeze": {k: round(w, 5) for k, w in held_w.items()},
                                "weights": {k: round(w, 5) for k, w in FM.matched_random_twin(
                                    held_w, sig, pool, seed).items()}}
                except FM.FleetRefusal as exc:
                    twin["error"] = str(exc)[:160]
            note = seal_status(role) if role in ("hack4", "hack6") else "loop down 2026-09-29: input not produced"
            c = FM.freeze_contract(v1_body(role, twin, note))
        else:
            c = FM.load_contract(role, "v1")
        out[f"{role}_v1"] = c["policy_hash"]
        c2 = FM.freeze_contract(v2_body(role, books)) if not FM.contract_file(role, "v2").exists() \
            else FM.load_contract(role, "v2")
        out[f"{role}_v2"] = c2["policy_hash"]
    return out


# ─────────────────────────────── main ───────────────────────────────────────

def print_role(r: dict) -> None:
    role = r["role"]
    if r.get("status") != "ok":
        print(f"{role}: {r.get('status')} {r.get('why', '')}")
        return
    print(f"\n=== {role} {r.get('account_number')}  equity ${r['equity']:,.0f}  cash ${r['cash']:,.0f}  "
          f"positions {r['n_positions']}  open orders {r['n_open_orders']}")
    ca = r["contract_active"]
    print(f"  contract ACTIVE {ca['version']} {ca['policy_hash']}: {ca['alpha_source'][:110]}")
    if r.get("contract_proposed"):
        cp = r["contract_proposed"]
        print(f"  contract PROPOSED {cp['version']} {cp['policy_hash']}: {cp['alpha_source'][:110]}")
    rc = r["reconcile"]
    print(f"  reconcile: {rc['status']} (since {rc.get('since')}, {rc.get('n_fills_since', 0)} fills; "
          f"foreign orders {len(rc.get('foreign_orders') or [])}; mismatches {rc.get('mismatches')})")
    for row in r.get("stop_table") or []:
        rs = "; ".join(f"stop {x['stop_price']} x{x['qty']} ({x['distance_frac']}, {x['distance_sigma']} sigma)"
                       for x in row["resting"]) or "NONE"
        print(f"  {row['symbol']:6s} {row['qty']:>8g} @ {row['price']:<9g} sigma {row['sigma_d'] or 0:.4f}  "
              f"target stop {row['target_stop_frac']:.3f}  resting: {rs}")
    for f in r.get("flags") or []:
        print(f"  FLAG {f}")
    wn, wa = r["worst_case_now"], r["worst_case_after_plan"]
    print(f"  WORST CASE now ${wn['worst_usd']:,.0f} ({wn['worst_pct_equity']}% of equity), gross/equity "
          f"{wn['gross_over_equity']}; after this run's plan ${wa['worst_usd']:,.0f} "
          f"({wa['worst_pct_equity']}%), gross/equity {wa['gross_over_equity']}")
    f1 = r.get("worst_case_formula_v1") or {}
    print(f"  formula v1 (declared book): {f1.get('n')} x {f1.get('notional_frac')} x {f1.get('stop_frac')} = "
          f"{f1.get('worst_frac')} -> ${f1.get('worst_usd', 0):,.0f}; gross {f1.get('gross_over_equity')}")
    if r.get("worst_case_formula_v2"):
        f2 = r["worst_case_formula_v2"]
        print(f"  formula v2 (proposal): {f2['n']} x {f2['notional_frac']} x {f2['stop_frac']} = "
              f"{f2['worst_frac']} -> ${f2['worst_usd']:,.0f}; gross {f2['gross_over_equity']}")
    for a in r.get("actions") or []:
        lp = f" limit {a['limit']}" if a.get("limit") else ""
        spx = f" stop {a['stop']}" if a.get("stop") else ""
        print(f"  [{a['mode']}] {a['kind']} {a['side']} {a['qty']} {a['symbol']}{lp}{spx} -- "
              f"{(a.get('refused') or a.get('reason') or '')[:120]} {a.get('outcome') or ''}")
    if r.get("grade"):
        g = r["grade"]
        print(f"  grade: {json.dumps({k: g.get(k) for k in ('session', 'account_return', 'spy_return', 'twin_return', 'vs_spy', 'vs_twin', 'status', 'error')})}")


def eod_audit_step(env: dict, run_id: str) -> dict:
    """Run the read-only end-of-day audit over EVERY fleet role (hack3 too, so a
    dead credential is named daily). A failure is a REFUSED block on the
    receipt, which the health reader turns DEGRADED -- never a silent skip."""
    try:
        from backend.services import fleet_eod_audit as EOD
        rows = EOD.run_audit(list(_cfg.FLEET_MANAGER_ROLES), env, run_id=run_id, trigger="preclose_pass")
        return {"status": "ok", "rows_written": len(rows), "file": str(EOD.audit_path().relative_to(FM.root())),
                "accounts": {r["role"]: r["status"] for r in rows}}
    except Exception as exc:                                    # noqa: BLE001 -- named on the receipt
        return {"status": f"REFUSED: {type(exc).__name__}: {exc}"[:300], "rows_written": 0}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="pass_", choices=("open", "preclose"), default="open")
    ap.add_argument("--live", action="store_true", help="allow LIVE where modes.json says LIVE")
    ap.add_argument("--roles", default=",".join(_cfg.FLEET_MANAGER_ROLES))
    ap.add_argument("--freeze", action="store_true", help="freeze missing contracts and exit")
    ap.add_argument("--rebaseline", default="", help="role(s) whose broker truth becomes the record")
    ap.add_argument("--log", default=str(FM.root() / "fleet_manager.log"))
    a = ap.parse_args(argv)
    setup_log(Path(a.log))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    print(f"\n##### fleet_manager run {run_id} pass={a.pass_} live_flag={a.live} "
          f"at {datetime.now().isoformat(timespec='seconds')} local")
    if FM.stop_file().exists():
        print(f"STOP file present ({FM.stop_file()}): nothing runs")
        return 3
    env = read_env_file(TERMINAL_ENV)
    roles = [r.strip() for r in a.roles.split(",") if r.strip()]
    books = read_books()
    if a.freeze:
        out = freeze_all(env, roles, books)
        print(json.dumps(out, indent=1))
        return 0
    modes = load_modes()
    freeze_all(env, [r for r in roles if not (modes.get(r) or {}).get("skip")
                     and not ((modes.get(r) or {}).get("not_before_utc") and datetime.now(timezone.utc)
                              < datetime.fromisoformat(modes[r]["not_before_utc"].replace("Z", "+00:00")))],
               books)
    issuer_of, iss_status = issuer_map_safe()
    stitched = stitched_safe()
    digest, digest_name = newest_digest()
    baseline = baseline_from_fleet_daily()
    reb = {r.strip() for r in a.rebaseline.split(",") if r.strip()}
    sector_of, sector_src = sector_map_safe()
    receipt: dict[str, Any] = {"schema": "fleet_manager_run/1", "run_id": run_id, "pass": a.pass_,
                               "live_flag": a.live, "started_utc": FM._now_iso(), "licence": FM.LICENCE,
                               "modes": modes, "issuer_map": iss_status, "n_stitched": len(stitched),
                               "digest": digest_name, "baseline": baseline[0], "gates": GATES_CFG,
                               "sector_map": sector_src, "accounts": []}
    rc = 0
    for role in roles:
        if FM.stop_file().exists():
            print("STOP file appeared: halting before", role)
            rc = 3
            break
        try:
            r = run_role(role, env=env, modes=modes, pass_=a.pass_, live_flag=a.live, run_id=run_id,
                         books=books, issuer_of=issuer_of, stitched=stitched, digest=digest,
                         digest_name=digest_name, baseline=baseline, pool={}, rebaseline=role in reb,
                         sector_of=sector_of)
        except Exception as exc:                                # noqa: BLE001 -- one account never stops the rest
            r = {"role": role, "status": "ERROR", "why": f"{type(exc).__name__}: {exc}"[:300],
                 "trace": traceback.format_exc()[-1500:]}
            rc = 1
        receipt["accounts"].append(r)
        print_role(r)
    # ── C26: the end-of-day audit is the Preclose pass's LAST step (read-only) ──
    if a.pass_ == "preclose":
        receipt["eod_audit"] = eod_audit_step(env, run_id)
    receipt["finished_utc"] = FM._now_iso()
    p = FM.root() / "runs" / f"run_{run_id}.json"
    FM.atomic_write_json(p, receipt)
    print(f"\nreceipt: {p}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
