"""Contest rehearsal, second and third books: ROT5_DIR (direction-filtered rotation) and the
runbook's fallback MAXTAIL_BH, plus the worst-case block, the 20% cap refusal, the live-desk
gate and the New York -> Hong Kong deadline arithmetic.

Why ROT5_DIR exists (owner, 2026-10-06): ROT5_TRAIL ranks reporters by the size of their past
earnings moves only. The names on top (NVEC, MAN, RHI, IRDM on the stock list) carried analyst
Sell/Hold consensus, so the book was, in effect, betting against the consensus on direction --
a choice never tested against its alternative. ROT5_DIR keeps ROT5_TRAIL's universe, sizing,
entry and exit, and only removes names whose analyst evidence points DOWN, re-ordering inside a
1-percentage-point magnitude bucket by revision momentum. Both books are frozen on the same
schedule and graded by the same grader, so the Oct 11 choice is measured, not argued.

The rule is a frozen contract (`RULES`), hashed into the rehearsal's freeze_log BEFORE its first
sheet. A changed rule under the same name REFUSES; a new version needs a new name.

PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. No LLM, no network, no
order anywhere: the owner types every contest ticket by hand.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc     # noqa: E402

NYZ = ZoneInfo("America/New_York")
HKZ = ZoneInfo("Asia/Hong_Kong")
ANALYST_REVISIONS = cc.OPT / "analyst" / "target_revisions.parquet"
LICENCE = "PRODUCT_EXPERIMENT"

# ───────────────────────────── the frozen rules ─────────────────────────────

BUY_GRADES = ("buy", "strong buy", "overweight", "outperform", "market outperform", "sector outperform",
              "positive", "accumulate", "add", "outperformer", "speculative buy", "top pick", "long-term buy",
              "conviction buy", "action list buy", "gradually accumulate", "above average")
HOLD_GRADES = ("neutral", "hold", "equal-weight", "market perform", "sector perform", "in-line", "peer perform",
               "perform", "sector weight", "market weight", "mixed", "fair value", "average", "sector performer",
               "hold neutral", "performer", "cautious")
SELL_GRADES = ("underweight", "underperform", "sell", "reduce", "negative", "sector underperform",
               "market underperform", "underperformer", "strong sell", "trim", "below average", "trading sell",
               "sector underweight")

RULES: dict[str, dict] = {
    "ROT5_DIR": {
        "strategy": "ROT5_DIR", "version": 1, "licence": LICENCE, "llm": "none",
        "declared_for": "contest rehearsal 2026-10, graded beside ROT5_TRAIL",
        "universe": "identical to ROT5_TRAIL: the desk's ranked reporters after contest_rehearsal.filter_ranked "
                    "(report in the sheet window, liquid, >= 3 past reactions, defect / estimated-date / "
                    "same-issuer refusals)",
        "sizing_and_exits": "identical to ROT5_TRAIL: 5 slots x min(20% NAV, $200k) at a limit 5% above the last "
                            "close; buy at the open before the print, sell at the open after it; no stop",
        "source": "backend/data/optimus/analyst/target_revisions.parquet (dated upgrades/downgrades and "
                  "target changes; each row carries its own event_date)",
        "point_in_time": "a row is used only if event_date < the sheet day 00:00 UTC AND event_date <= pulled_at",
        "consensus": "per firm, its latest to_grade in the 365 days before the sheet day; Buy family +1, "
                     "Hold family 0, Sell family -1, unknown grades ignored; cons = mean over firms",
        "revision_flow": "rows dated in the 90 days before the sheet day: +1 if action is 'up' or the target "
                         "Raises, -1 if action is 'down' or the target Lowers, 0 if both or neither; "
                         "net_raises = sum; rev_mom = net_raises / rows with a sign (0 when none)",
        "drop": ["cons < 0 (net Sell consensus)", "net_raises < 0 (net lowering over 90 days)"],
        "unrated": "no rating in 365 days and no signed flow in 90 days (every non-US listing: the pull is "
                   "US-only) -> ADMITTED as UNRATED with cons 0 and rev_mom 0; no direction evidence either way",
        "order": "bucket = floor(trail_abs x 100) descending (magnitude kept at 1 pp resolution), then rev_mom "
                 "descending, then cons descending, then trail_abs descending",
        "long_only": True,
        "max_source_age_days": 14,
        "grade_map": {"buy": list(BUY_GRADES), "hold": list(HOLD_GRADES), "sell": list(SELL_GRADES)},
        "chosen_after_looking": "written 2026-10-07 from the owner's criticism (four names on one stock list) and "
                                "the task statement, before any ROT5_DIR sheet existed. The builder had seen the "
                                "ROT5_TRAIL scoreboard (6 closed positions); no parameter was tuned on it. The "
                                "thresholds (cons < 0, net < 0, 365 / 90 days, 1 pp bucket) are round, not fitted",
    },
    "MAXTAIL_BH": {
        "strategy": "MAXTAIL_BH", "version": 1, "licence": LICENCE, "llm": "none",
        "declared_for": "the runbook's fallback, graded beside the two rotations",
        "definition": "runbook: the 5 highest-volatility names, bought once and held "
                      "(contest_strategy_lab MAXTAIL_BH: liquid operating companies, highest sigma63 on the "
                      "window's first day, held to the end)",
        "universe": "panel names with median $ volume >= the desk's liquidity floor, price >= $1, >= 3 past "
                    "earnings reactions (operating company), not defect-flagged or stitched, not NOT_IN_WLS, "
                    "one line per issuer, whose next session opens inside the sheet window",
        "rank": "sigma63 EXCLUDING the window's single largest |move| (daily log-return s.d. over the last 63 own "
                "sessions before the sheet day, >= 40 needed), descending",
        "why_ex_max": "set before the contract was frozen, after the first DRY preview (2026-10-07) ranked three "
                      "one-jump series on top by raw sigma63 (CTVA x6.2 on 2026-10-01, SION x11 on 2026-08-10, "
                      "MRNA x2.8 on 2026-08-19: splits / spin-offs / bad prints). A data-validity choice; no "
                      "outcome was read",
        "sizing": "5 x min(20% NAV, $200k) at a limit 5% above the last close",
        "buys": "on its FIRST sheet only; later sheets carry no BUY",
        "exit": "the first session of each listing after the book's last buying sheet day (rehearsal: the "
                "wind-down; contest: not traded by this module)",
    },
}
STRATEGIES = tuple(RULES)
STOP_REFERENCE = (0.05, 0.10)      # hypothetical stops for the worst-case print; ROT5 has none


class DirectionRefused(RuntimeError):
    """The direction source cannot support a sheet (missing, unreadable or too old)."""


class ContractChanged(RuntimeError):
    """A frozen strategy contract was edited under the same name."""


class CapRefused(ValueError):
    """A ticket or a book that breaks the public 20% / no-leverage rules."""


class LiveGateRefused(RuntimeError):
    """The live order sheet is refused until the owner's two hand-made preconditions exist."""


def contract_sha(name: str) -> str:
    return hashlib.sha256(json.dumps(RULES[name], sort_keys=True).encode("utf-8")).hexdigest()


def ensure_contract(name: str, log: Path, *, now_utc: Optional[str] = None) -> dict:
    """Append the contract to the freeze log once. Same hash -> no-op; a different hash under the
    same name -> ContractChanged (a frozen rule is never edited in place)."""
    sha = contract_sha(name)
    log = Path(log)
    if log.exists():
        for ln in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("kind") == "STRATEGY_CONTRACT" and r.get("strategy") == name:
                if r.get("contract_sha256") != sha:
                    raise ContractChanged(f"{name}: frozen contract {r.get('contract_sha256', '')[:16]} "
                                          f"differs from the code's {sha[:16]}; declare a new name/version")
                return r
    rec = {"kind": "STRATEGY_CONTRACT", "strategy": name, "version": RULES[name]["version"],
           "contract_sha256": sha, "declared_utc": now_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
           "licence": LICENCE, "rule": RULES[name]}
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


# ───────────────────────────── ROT5_DIR: direction from dated analyst rows ─────────────────────────────

def grade_sign(g: Any) -> Optional[int]:
    s = str(g or "").strip().lower()
    if s in BUY_GRADES:
        return 1
    if s in HOLD_GRADES:
        return 0
    if s in SELL_GRADES:
        return -1
    return None


def load_revisions(path: Path = ANALYST_REVISIONS) -> pd.DataFrame:
    if not Path(path).exists():
        raise DirectionRefused(f"direction source missing: {path}")
    try:
        d = pd.read_parquet(path, columns=["ticker", "pulled_at", "event_date", "firm", "to_grade",
                                           "action", "target_action"])
    except Exception as exc:                                   # noqa: BLE001
        raise DirectionRefused(f"direction source unreadable: {type(exc).__name__}: {exc}") from exc
    return d


def analyst_direction(symbols: Iterable[str], asof: date, rev: pd.DataFrame, *,
                      now_utc: Optional[pd.Timestamp] = None) -> tuple[pd.DataFrame, dict]:
    """Per symbol: n_firms, n_buy, n_hold, n_sell, cons, n_flow, net_raises, rev_mom, verdict.
    Raises DirectionRefused when the source is older than the contract allows."""
    rule = RULES["ROT5_DIR"]
    syms = [str(s).upper() for s in symbols]
    now_utc = now_utc if now_utc is not None else pd.Timestamp.now(tz="UTC")
    pulled = pd.to_datetime(rev["pulled_at"], utc=True, errors="coerce")
    last_pull = pulled.max()
    if pd.isna(last_pull):
        raise DirectionRefused("direction source has no pulled_at stamp")
    age = (now_utc - last_pull).total_seconds() / 86400.0
    meta = {"source": str(ANALYST_REVISIONS.relative_to(REPO)) if ANALYST_REVISIONS.is_relative_to(REPO) else
            str(ANALYST_REVISIONS), "last_pulled_utc": str(last_pull), "source_age_days": round(age, 2),
            "max_source_age_days": rule["max_source_age_days"]}
    if age > rule["max_source_age_days"]:
        raise DirectionRefused(f"direction source is {age:.1f} days old (> {rule['max_source_age_days']}): "
                               "re-run scripts/pull_analyst_targets before a ROT5_DIR sheet")
    d = rev[rev["ticker"].astype(str).str.upper().isin(set(syms))].copy()
    d["ticker"] = d["ticker"].astype(str).str.upper()
    ev = pd.to_datetime(d["event_date"], errors="coerce", utc=True)
    pu = pd.to_datetime(d["pulled_at"], errors="coerce", utc=True)
    day0 = pd.Timestamp(asof, tz="UTC")
    future = int(((ev > pu) & ev.notna()).sum())
    keep = ev.notna() & (ev < day0) & (ev <= pu)
    d, ev = d[keep], ev[keep]
    meta["rows_dated_after_their_pull_excluded"] = future
    rows = []
    for s in syms:
        g = d[d.ticker == s]
        e = ev[d.ticker == s]
        # consensus: each firm's latest grade within 365 days
        gc = g[e >= day0 - pd.Timedelta(days=365)].assign(_t=e[e >= day0 - pd.Timedelta(days=365)])
        latest = gc.sort_values("_t").groupby("firm").tail(1) if len(gc) else gc
        signs = [x for x in (grade_sign(v) for v in latest.get("to_grade", [])) if x is not None]
        nb, nh, ns = signs.count(1), signs.count(0), signs.count(-1)
        cons = float(np.mean(signs)) if signs else 0.0
        # flow: signed rows within 90 days
        gf = g[e >= day0 - pd.Timedelta(days=90)]
        up = gf["action"].astype(str).str.lower().eq("up") | gf["target_action"].astype(str).str.lower().eq("raises")
        dn = gf["action"].astype(str).str.lower().eq("down") | gf["target_action"].astype(str).str.lower().eq("lowers")
        sgn = up.astype(int) - dn.astype(int)
        n_flow = int((sgn != 0).sum())
        net = int(sgn.sum())
        mom = net / n_flow if n_flow else 0.0
        if not signs and n_flow == 0:
            verdict = "UNRATED"
        elif cons < 0:
            verdict = "DROP_NET_SELL"
        elif net < 0:
            verdict = "DROP_NET_LOWERING"
        else:
            verdict = "ADMIT"
        rows.append({"symbol": s, "n_firms": len(signs), "n_buy": nb, "n_hold": nh, "n_sell": ns,
                     "cons": round(cons, 4), "n_flow90": n_flow, "net_raises90": net, "rev_mom": round(mom, 4),
                     "verdict": verdict})
    return pd.DataFrame(rows, columns=["symbol", "n_firms", "n_buy", "n_hold", "n_sell", "cons", "n_flow90",
                                       "net_raises90", "rev_mom", "verdict"]), meta


def direction_rank(ranked: pd.DataFrame, asof: date, *, rev: Optional[pd.DataFrame] = None,
                   now_utc: Optional[pd.Timestamp] = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """ROT5_TRAIL's ranked frame -> (ROT5_DIR ranked frame, dropped-with-reason, meta)."""
    if ranked is None or ranked.empty:
        return ranked, pd.DataFrame(), {"note": "no ranked names"}
    rev = load_revisions() if rev is None else rev
    dirn, meta = analyst_direction(ranked.symbol, asof, rev, now_utc=now_utc)
    r = ranked.copy()
    r["_S"] = r.symbol.astype(str).str.upper()
    r = r.merge(dirn.rename(columns={"symbol": "_S"}), on="_S", how="left")
    dropped = r[r.verdict.astype(str).str.startswith("DROP")].copy()
    dropped["refusal"] = [f"ROT5_DIR_{v} (cons {c:+.2f} over {n} firms; 90d net raises {k:+d})"
                          for v, c, n, k in zip(dropped.verdict, dropped.cons, dropped.n_firms, dropped.net_raises90)]
    keep = r[~r.verdict.astype(str).str.startswith("DROP")].copy()
    keep["mag_bucket"] = np.floor(keep["trail_abs"].astype(float) * 100.0)
    keep = keep.sort_values(["mag_bucket", "rev_mom", "cons", "trail_abs"],
                            ascending=[False, False, False, False], kind="mergesort").reset_index(drop=True)
    keep["trail_rank"] = keep.get("rank")
    keep["rank"] = np.arange(1, len(keep) + 1)
    meta.update(n_in=int(len(ranked)), n_admitted=int((keep.verdict == "ADMIT").sum()),
                n_unrated=int((keep.verdict == "UNRATED").sum()), n_dropped=int(len(dropped)),
                contract_sha256=contract_sha("ROT5_DIR"))
    return keep.drop(columns=["_S"]), dropped.drop(columns=["_S"]), meta


# ───────────────────────────── MAXTAIL_BH ─────────────────────────────

def maxtail_ranked(day: date, panel: Any, events: pd.DataFrame, universe: Optional[pd.DataFrame], *,
                   liq_floor: float = cc.LIQ_FLOOR_USD, top: int = 40) -> pd.DataFrame:
    """The runbook fallback's candidates on `day`: liquid operating names by sigma63, highest first.
    Columns: symbol, sig63, dv63, price_usd, name, bbg_ticker, membership, market."""
    i = panel.idx(pd.Timestamp(day) - pd.Timedelta(days=1))
    if i < 0:
        return pd.DataFrame()
    if events is None or not len(events):
        return pd.DataFrame()
    nrep = events[events.absr.notna()].groupby("symbol").size() if len(events) and "absr" in events else pd.Series()
    oper = set(nrep[nrep >= 3].index)
    last_close = pd.DataFrame(panel.close[max(0, i - 7): i + 1, :]).ffill().iloc[-1].to_numpy()
    df = pd.DataFrame({"symbol": list(panel.syms), "sig63": panel.sig63[i, :], "dv63": panel.dv63[i, :],
                       "price_usd": last_close, "market": panel.market})
    df = df[df.symbol.isin(oper) & np.isfinite(df.sig63) & (df.dv63.fillna(0) >= liq_floor)
            & (df.price_usd.fillna(0) >= 1.0)]
    cut = cc.stitched_cut_symbols()
    df = df[~df.symbol.isin(cut)]
    if universe is not None and len(universe):
        u = universe.drop_duplicates("symbol").set_index("symbol")
        for col in ("name", "bbg_ticker", "membership"):
            df[col] = df.symbol.map(u[col]) if col in u.columns else None
    else:
        df["name"], df["bbg_ticker"], df["membership"] = None, None, "UNCONFIRMED_MEMBERSHIP"
    df["bbg_ticker"] = df["bbg_ticker"].fillna(df.symbol.map(cc.bloomberg_ticker))
    df["membership"] = df["membership"].fillna("UNCONFIRMED_MEMBERSHIP")
    df = df[df.membership != "NOT_IN_WLS_EXPORT"]
    df["sig63_raw"] = df["sig63"]
    df["sig63"] = [sigma_ex_max(panel, panel.col[s], i) for s in df.symbol]
    df["max_abs_logret63"] = [max_abs_logret(panel, panel.col[s], i) for s in df.symbol]
    df = df[np.isfinite(df.sig63)]
    return df.sort_values("sig63", ascending=False, kind="mergesort").head(top).reset_index(drop=True)


def _own_logrets(panel: Any, j: int, i: int, n: int = 63) -> np.ndarray:
    c = panel.close[: i + 1, j]
    c = c[np.isfinite(c) & (c > 0)][-(n + 1):]
    return np.diff(np.log(c.astype(float))) if len(c) > 1 else np.array([])


def sigma_ex_max(panel: Any, j: int, i: int, n: int = 63) -> float:
    """sigma63 without the window's single largest |move|: one jump (a split, a spin-off, a bad print,
    or one real event) does not make a volatile name. Needs 40 sessions, like sigma63."""
    r = _own_logrets(panel, j, i, n)
    if len(r) < 40:
        return float("nan")
    r = np.delete(r, int(np.argmax(np.abs(r))))
    return float(np.std(r, ddof=1))


def max_abs_logret(panel: Any, j: int, i: int, n: int = 63) -> float:
    r = _own_logrets(panel, j, i, n)
    return float(np.max(np.abs(r))) if len(r) else float("nan")


# ───────────────────────────── worst case and the cap ─────────────────────────────

def worst_case(*, nav_usd: float, cap_binding: float, book: list[dict], k: int = 5,
               stops: tuple = STOP_REFERENCE) -> dict:
    """Protocol item 4. `book`: one dict per name held after the sheet's tickets with notional_usd,
    sig63 (daily, may be NaN) and trail_abs (mean |earnings reaction|, may be NaN)."""
    largest = k * cap_binding
    sig = [float(b.get("sig63")) for b in book if b.get("sig63") is not None and np.isfinite(b.get("sig63"))]
    trl = [float(b.get("trail_abs")) for b in book if b.get("trail_abs") is not None
           and np.isfinite(b.get("trail_abs"))]
    gross = float(sum(abs(float(b.get("notional_usd") or 0.0)) for b in book))
    out = {"nav_usd": round(nav_usd, 2), "k": k, "cap_binding_usd": round(cap_binding, 2),
           "largest_admissible_gross_usd": round(largest, 2),
           "largest_admissible_gross_over_equity": round(largest / nav_usd, 4) if nav_usd else None,
           "largest_at_stop_usd": {f"{s:.0%}": round(-largest * s, 2) for s in stops},
           "largest_at_2sigma63_usd": round(-largest * 2 * max(sig), 2) if sig else None,
           "largest_at_2sigma63_basis": "the largest sigma63 among this sheet's book names" if sig else "n/a",
           "book_n": len(book), "book_gross_usd": round(gross, 2),
           "book_gross_over_equity": round(gross / nav_usd, 4) if nav_usd else None,
           "book_at_stop_usd": {f"{s:.0%}": round(-gross * s, 2) for s in stops},
           "book_at_2sigma63_usd": round(-sum(abs(float(b.get("notional_usd") or 0)) * 2 * float(b["sig63"])
                                              for b in book if b.get("sig63") is not None
                                              and np.isfinite(b["sig63"])), 2) if sig else None,
           "book_at_2x_trailing_move_usd": round(-sum(abs(float(b.get("notional_usd") or 0)) * 2 * float(b["trail_abs"])
                                                      for b in book if b.get("trail_abs") is not None
                                                      and np.isfinite(b["trail_abs"])), 2) if trl else None,
           "stop_note": "No book here carries a stop (ROT5 exits at the open after the print; MAXTAIL holds) and a gap fills "
                        "through any stop: the stop rows are reference arithmetic, not a bound"}
    return out


def worst_case_lines(w: dict, label: str) -> list[str]:
    st = "; ".join(f"{k} stop ${-v:,.0f}" for k, v in w["largest_at_stop_usd"].items())
    bs = "; ".join(f"{k} stop ${-v:,.0f}" for k, v in w["book_at_stop_usd"].items())
    two = "n/a" if w["largest_at_2sigma63_usd"] is None else f"${-w['largest_at_2sigma63_usd']:,.0f}"
    b2 = "n/a" if w["book_at_2sigma63_usd"] is None else f"${-w['book_at_2sigma63_usd']:,.0f}"
    bt = "n/a" if w["book_at_2x_trailing_move_usd"] is None else f"${-w['book_at_2x_trailing_move_usd']:,.0f}"
    return [f"**WORST CASE ({label})** largest admissible book {w['k']} x ${w['cap_binding_usd']:,.0f} = "
            f"${w['largest_admissible_gross_usd']:,.0f}, sum|notional|/equity "
            f"{w['largest_admissible_gross_over_equity']:.2f}: loss at {st}; at a 2-sigma63 move {two} "
            f"({w['largest_at_2sigma63_basis']}).",
            f"This sheet's book after its tickets: {w['book_n']} name(s), ${w['book_gross_usd']:,.0f} gross = "
            f"{w['book_gross_over_equity']:.2f} of equity; loss at {bs}; at 2-sigma63 {b2}; at 2x the trailing "
            f"|earnings move| {bt}. {w['stop_note']}."]


def assert_cap(tickets: list, *, nav_usd: float, cap_binding: float, held_notional_usd: float = 0.0,
               notional_usd: float = 1_000_000.0, cap: float = 0.20) -> None:
    """Public rule: no single position above 20% of the notional at entry; long only; no leverage."""
    limit = min(cap * notional_usd, cap_binding)
    buys = [t for t in tickets if getattr(t, "side", None) == "BUY" and getattr(t, "status", "") != "VOID_LATE"]
    for t in buys:
        if int(t.qty) <= 0:
            raise CapRefused(f"{t.bbg}: non-positive quantity {t.qty} (long only)")
        if float(t.notional_usd) > limit + 1e-6:
            raise CapRefused(f"{t.bbg}: ${float(t.notional_usd):,.0f} at entry exceeds the 20% cap ${limit:,.0f}")
    gross = held_notional_usd + sum(float(t.notional_usd) for t in buys)
    if gross > max(nav_usd, 0.0) + 1e-6:
        raise CapRefused(f"gross ${gross:,.0f} exceeds NAV ${nav_usd:,.0f} (no leverage)")


# ───────────────────────────── the live gate ─────────────────────────────

def live_gate(contest_dir: Optional[Path] = None) -> tuple[bool, list[str]]:
    """The live order sheet needs (D1) a WLS MEMB export in contest/wls/ and (registration) the file
    contest/REGISTERED, created by hand by the owner after confirming registration."""
    contest_dir = Path(contest_dir) if contest_dir is not None else cc.CONTEST
    reasons = []
    try:
        w = cc.load_wls_export(Path(contest_dir) / "wls")
        if w is None or len(w) == 0:
            reasons.append("no WLS membership (MEMB) export in contest/wls/ (owner decision D1)")
    except Exception as exc:                                   # noqa: BLE001
        reasons.append(f"WLS export in contest/wls/ is unreadable: {type(exc).__name__}: {exc}")
    if not (Path(contest_dir) / "REGISTERED").exists():
        reasons.append("contest/REGISTERED is missing (the owner creates it by hand after confirming the "
                       "team's registration)")
    return (not reasons), reasons


def gate_receipt(reasons: list[str], day: date, *, contest_dir: Optional[Path] = None) -> Path:
    contest_dir = Path(contest_dir) if contest_dir is not None else cc.CONTEST
    out = Path(contest_dir) / "live" / "refusals"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = out / f"live_gate_{day}_{stamp}.json"
    p.write_text(json.dumps({"receipt": "contest_live_gate", "day": str(day), "written_utc": stamp,
                             "result": "REFUSED", "reasons": reasons, "places_orders": False}, indent=1),
                 encoding="utf-8")
    log = Path(contest_dir) / "logs" / "contest_live_gate.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {day} REFUSED: {' | '.join(reasons)}\n")
    return p


# ───────────────────────────── New York times -> Hong Kong ─────────────────────────────

CONTEST_TIMES_NY = {
    "registration_closes": datetime(2026, 10, 4, 23, 59),
    "contest_starts": datetime(2026, 10, 12, 9, 0),
    "initial_positions_due": datetime(2026, 10, 16, 23, 59),
    "contest_ends": datetime(2026, 11, 13, 17, 0),
}


def ny_to_hkt(dt_ny: datetime) -> datetime:
    """A naive New York wall time -> Hong Kong wall time (zoneinfo applies the US DST rule)."""
    return dt_ny.replace(tzinfo=NYZ).astimezone(HKZ)


def contest_times() -> dict:
    return {k: {"ny": v.replace(tzinfo=NYZ), "hkt": ny_to_hkt(v), "utc": v.replace(tzinfo=NYZ).astimezone(timezone.utc)}
            for k, v in CONTEST_TIMES_NY.items()}


def contest_start_utc() -> pd.Timestamp:
    return pd.Timestamp(CONTEST_TIMES_NY["contest_starts"]).tz_localize(NYZ).tz_convert("UTC")


def freeze_time_et(day: date, *, hour: int = 14, minute: int = 30) -> datetime:
    """The scheduled freeze (14:30 HKT on `day`) in New York time."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=HKZ).astimezone(NYZ)


def us_open_et(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 30, tzinfo=NYZ)
