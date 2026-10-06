"""Contest books beside ROT5_TRAIL: ROT5_DIR (direction-filtered rotation), the runbook's fallback
MAXTAIL_BH and the review's MAXTAIL_EVT, plus the worst-case block, the 20% cap refusal, the
live-desk gate (WLS MEMB + REGISTERED), the BOOK-file reader and the New York -> Hong Kong times.

Why ROT5_DIR exists (owner, 2026-10-06): ROT5_TRAIL ranks reporters by the size of their past
earnings moves only. The names on top (NVEC, MAN, RHI, IRDM on the stock list) carried analyst
Sell/Hold consensus, so the book was, in effect, betting against the consensus on direction --
a choice never tested against its alternative. ROT5_DIR keeps ROT5_TRAIL's universe, sizing,
entry and exit, and only removes names whose analyst evidence points DOWN, re-ordering inside a
1-percentage-point magnitude bucket by revision momentum. Both books are frozen on the same
schedule and graded by the same grader, so the Oct 11 choice is measured, not argued.

Each rule is a frozen contract: the policy hash is sha256(rule text | the code of this module and
contest_rehearsal.py), appended to the rehearsal's freeze_log BEFORE its first sheet. A change to
the rule OR the code under the same (name, version) REFUSES; a new version records what it
supersedes (v2, 2026-10-07: REVIEW_2026-10-06_C9 F1/F6/F7).

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

_V1 = {"ROT5_DIR": "7d7cb923ec31b5d04e0b04d1e2c3e09492b52b843e19bac276da6e2ba85a2c8b",
       "MAXTAIL_BH": "1307374645d6d86eb7247d7ca30a9528b0ef85fdf5840299fed4ac0c5822a7f1"}
JUMP_LOG = float(np.log(2.0))          # a one-day close ratio of x2 (or 1/2) or more is a data defect
EVT_WINDOW = (date(2026, 10, 13), date(2026, 11, 12))
EVT_STATUSES = ("VENDOR_ANNOUNCED", "CONFIRMED_EXCHANGE")
BOOKS_LIVE = ("ROT5_TRAIL", "ROT5_DIR", "MAXTAIL_BH", "MAXTAIL_EVT")

_MAXTAIL_COMMON = {
    "universe": "panel names with median $ volume >= the desk's liquidity floor, price >= $1, >= 3 past "
                "earnings reactions (operating company), not defect-flagged or stitched, not NOT_IN_WLS, "
                "one line per issuer, whose next session opens inside the sheet window (contest: at or after "
                "the 09:00 NY start)",
    "rank": "RAW sigma63 (the panel's daily log-return s.d. over 63 own sessions, as of the last bar before "
            "the sheet day), descending -- the same measure contest_strategy_lab ranks MAXTAIL on",
    "data_defect_refusal": "a series with any one-day |log close ratio| >= log 2 (x2 up or halved) inside its "
                           "last 63 own sessions is REFUSED_JUMP_X2 and printed on the sheet: a split, spin-off, "
                           "stitch or bad print makes its sigma, its sizing and its grade wrong. The same rule is "
                           "applied in contest_strategy_lab",
    "sizing": "5 x min(20% NAV, $200k) at a limit 5% above the last close before the sheet day",
    "buys": "once: on the book's first sheet with a buy session in its window; later sheets carry no BUY",
    "exit": "rehearsal: the first open after the last buying sheet's window (the wind-down); contest: held to "
            "the end (no SELL ticket inside the contest)",
    "stop": "none; the drift line prints the trim if the 20% cap applies at all times (OWNER-ONLY item 4)",
}

RULES: dict[str, dict] = {
    "ROT5_DIR": {
        "strategy": "ROT5_DIR", "version": 2, "supersedes": _V1["ROT5_DIR"], "licence": LICENCE, "llm": "none",
        "declared_for": "contest rehearsal 2026-10, graded beside ROT5_TRAIL; selectable live via contest/live/BOOK",
        "universe": "identical to ROT5_TRAIL: the desk's ranked reporters after contest_rehearsal.filter_ranked "
                    "(report in the sheet window, liquid, >= 3 past reactions, defect / estimated-date / "
                    "same-issuer refusals)",
        "sizing_and_exits": "identical to ROT5_TRAIL: 5 slots x min(20% NAV, $200k) at a limit 5% above the last "
                            "close; buy at the open before the print, sell at the open after it; no stop",
        "source": "backend/data/optimus/analyst/target_revisions.parquet (dated upgrades/downgrades and "
                  "target changes); its sha256 and row count are printed on every sheet",
        "point_in_time": "a row is used only if event_date < the sheet day 00:00 UTC AND first_seen_utc <= the "
                         "freeze time. first_seen_utc is the first pull that served the row (min semantics, kept "
                         "by pull_analyst_targets from 2026-10-07); rows from before the column existed carry "
                         "their last pulled_at, an UPPER bound on when they were known",
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
        "on_refusal": "shadow sheet: REFUSED with the reason; contest live sheet: falls back to ROT5_TRAIL with a "
                      "banner and contest/live/REFUSED_<day>.txt (a day is never lost to the filter)",
        "grade_map": {"buy": list(BUY_GRADES), "hold": list(HOLD_GRADES), "sell": list(SELL_GRADES)},
        "chosen_after_looking": "v1 written 2026-10-07 from the owner's criticism and the task statement; v2 "
                                "changes only the point-in-time guard (first_seen) and the source fingerprint, "
                                "after the adversarial review. The thresholds are round, not fitted. The "
                                "reviewer's event-level replay (top-5, 2019+: 28% dropped, dropped names -0.45 "
                                "pp/event, t -1.33, fatter tails both sides) was read BEFORE v2; v2 does not "
                                "change any threshold because of it",
    },
    "MAXTAIL_BH": {
        "strategy": "MAXTAIL_BH", "version": 2, "supersedes": _V1["MAXTAIL_BH"], "licence": LICENCE, "llm": "none",
        "declared_for": "the runbook's fallback; rehearsal shadow book and a contest book via contest/live/BOOK",
        "definition": "runbook: the 5 highest-volatility names, bought once and held (contest_strategy_lab "
                      "MAXTAIL_BH: liquid operating companies, highest sigma63 on the window's first day, held)",
        **_MAXTAIL_COMMON,
        "v1_to_v2": "v1 ranked on sigma63 excluding the largest move, chosen after reading a preview; the review "
                    "(F7) called it a prior chosen after looking. v2 reverts to the lab's RAW measure and moves the "
                    "fix to the data layer (REFUSED_JUMP_X2). No outcome was read for either",
    },
    "MAXTAIL_EVT": {
        "strategy": "MAXTAIL_EVT", "version": 1, "licence": LICENCE, "llm": "none",
        "declared_for": "the adversarial review's proposal MAXTAIL_EVT_v1 (REVIEW_2026-10-06_C9 'what I would "
                        "freeze instead'); rehearsal shadow book and a contest book via contest/live/BOOK",
        **_MAXTAIL_COMMON,
        "event_filter": "US listings only, whose latest contest calendar (contest/calendar/calendar_*.parquet) "
                        "carries a VENDOR_ANNOUNCED or CONFIRMED_EXCHANGE date between 2026-10-13 and "
                        "2026-11-12: every name holds one print inside the contest",
        "why": "diffusive variance plus one event gap per name, turnover ~1x instead of ~50x (commissions "
               "item 2 nearly irrelevant), one entry day (the operational risk of daily typing removed)",
        "lab_gate": "contest_strategy_lab line MAXTAIL_EVT (reporters in the window only, hold) is run beside "
                    "MAXTAIL_BH and ROT5_TRAIL; read the worst cell and P(>+40%), not the median",
    },
}
STRATEGIES = tuple(RULES)
STOP_REFERENCE = (0.05, 0.10)      # hypothetical stops for the worst-case print; no book here has one
CODE_FILES = (Path(__file__).resolve(), Path(__file__).resolve().with_name("contest_rehearsal.py"))


class DirectionRefused(RuntimeError):
    """The direction source cannot support a sheet (missing, unreadable or too old)."""


class ContractChanged(RuntimeError):
    """A frozen strategy contract was edited under the same name and version."""


class CapRefused(ValueError):
    """A ticket or a book that breaks the public 20% / no-leverage rules."""


class LiveGateRefused(RuntimeError):
    """The live order sheet is refused until the owner's two hand-made preconditions exist."""


def rule_sha(name: str) -> str:
    return hashlib.sha256(json.dumps(RULES[name], sort_keys=True).encode("utf-8")).hexdigest()


def code_sha(files: Optional[Iterable[Path]] = None) -> str:
    """sha256 over the strategy code that runs (line endings normalised, so a CRLF checkout hashes the same)."""
    h = hashlib.sha256()
    for f in (CODE_FILES if files is None else files):
        h.update(Path(f).name.encode("utf-8") + b"\0")
        h.update(Path(f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def contract_sha(name: str) -> str:
    """The policy hash: the rule text AND the code that executes it."""
    return hashlib.sha256(f"{rule_sha(name)}|{code_sha()}".encode("utf-8")).hexdigest()


def ensure_contract(name: str, log: Path, *, now_utc: Optional[str] = None) -> dict:
    """Append the contract to the freeze log once per (strategy, version). The same hash -> no-op; a
    different hash under the same name AND version -> ContractChanged (a frozen rule or its code is
    never edited in place: bump the version, which records what it supersedes)."""
    sha = contract_sha(name)
    ver = RULES[name]["version"]
    log = Path(log)
    prev = None
    if log.exists():
        for ln in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("kind") == "STRATEGY_CONTRACT" and r.get("strategy") == name:
                if r.get("version", 1) == ver:
                    if r.get("contract_sha256") != sha:
                        raise ContractChanged(f"{name} v{ver}: frozen contract {r.get('contract_sha256', '')[:16]} "
                                              f"differs from the code's {sha[:16]}; bump the version")
                    return r
                prev = r
    rec = {"kind": "STRATEGY_CONTRACT", "strategy": name, "version": ver, "contract_sha256": sha,
           "rule_sha256": rule_sha(name), "code_sha256": code_sha(),
           "code_files": [Path(f).name for f in CODE_FILES],
           "supersedes": (prev or {}).get("contract_sha256"),
           "declared_utc": now_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
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
    """The dated analyst rows plus `first_seen_utc` (the column when the pull wrote it; else the row's
    pulled_at, an upper bound) and `attrs['fingerprint']` = the file's sha256 and row count."""
    if not Path(path).exists():
        raise DirectionRefused(f"direction source missing: {path}")
    try:
        cols = pq_columns(path)
        want = ["ticker", "pulled_at", "event_date", "firm", "to_grade", "action", "target_action"]
        d = pd.read_parquet(path, columns=want + (["first_seen_utc"] if "first_seen_utc" in cols else []))
    except Exception as exc:                                   # noqa: BLE001
        raise DirectionRefused(f"direction source unreadable: {type(exc).__name__}: {exc}") from exc
    if "first_seen_utc" not in d.columns:
        d["first_seen_utc"] = d["pulled_at"]
        basis = "pulled_at (no first_seen column yet: an upper bound on when each row was known)"
    else:
        d["first_seen_utc"] = d["first_seen_utc"].fillna(d["pulled_at"])
        basis = "first_seen_utc (min over pulls; pulled_at where missing)"
    d.attrs["fingerprint"] = {"file": Path(path).name, "sha256": file_sha256(path), "rows": int(len(d)),
                              "first_seen_basis": basis}
    return d


def pq_columns(path: Path) -> list[str]:
    import pyarrow.parquet as pq                               # noqa: PLC0415
    return list(pq.ParquetFile(path).schema_arrow.names)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frame_fingerprint(d: pd.DataFrame) -> dict:
    if d.attrs.get("fingerprint"):
        return dict(d.attrs["fingerprint"])
    v = pd.util.hash_pandas_object(d.astype(str), index=False).to_numpy()
    return {"file": "(in-memory frame)", "sha256": hashlib.sha256(v.tobytes()).hexdigest(), "rows": int(len(d)),
            "first_seen_basis": "first_seen_utc" if "first_seen_utc" in d.columns else "pulled_at"}


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
    meta = {"source": "backend/data/optimus/analyst/target_revisions.parquet", "last_pulled_utc": str(last_pull),
            "source_age_days": round(age, 2), "max_source_age_days": rule["max_source_age_days"],
            "fingerprint": frame_fingerprint(rev)}
    if age > rule["max_source_age_days"]:
        raise DirectionRefused(f"direction source is {age:.1f} days old (> {rule['max_source_age_days']}): "
                               "re-run scripts/pull_analyst_targets before a ROT5_DIR sheet")
    d = rev[rev["ticker"].astype(str).str.upper().isin(set(syms))].copy()
    d["ticker"] = d["ticker"].astype(str).str.upper()
    ev = pd.to_datetime(d["event_date"], errors="coerce", utc=True)
    fs_col = d["first_seen_utc"] if "first_seen_utc" in d.columns else d["pulled_at"]
    fs = pd.to_datetime(fs_col, errors="coerce", utc=True)
    day0 = pd.Timestamp(asof, tz="UTC")
    late = int((ev.notna() & (ev < day0) & ~(fs <= now_utc)).sum())
    keep = ev.notna() & (ev < day0) & (fs <= now_utc)
    d, ev = d[keep], ev[keep]
    meta["rows_first_seen_after_the_freeze_excluded"] = late
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


# ───────────────────────────── MAXTAIL_BH / MAXTAIL_EVT ─────────────────────────────

def maxtail_ranked(day: date, panel: Any, events: pd.DataFrame, universe: Optional[pd.DataFrame], *,
                   liq_floor: float = cc.LIQ_FLOOR_USD, top: int = 40,
                   only: Optional[set] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MAXTAIL candidates on `day`: liquid operating names by RAW sigma63, highest first, after the
    data-defect refusal (a x2 one-day move inside 63 own sessions). `only`: restrict to these symbols
    (MAXTAIL_EVT). Returns (ranked, refused_jump)."""
    empty = (pd.DataFrame(), pd.DataFrame())
    i = panel.idx(pd.Timestamp(day) - pd.Timedelta(days=1))
    if i < 0 or events is None or not len(events) or "absr" not in events:
        return empty
    nrep = events[events.absr.notna()].groupby("symbol").size()
    oper = set(nrep[nrep >= 3].index)
    last_close = pd.DataFrame(panel.close[max(0, i - 7): i + 1, :]).ffill().iloc[-1].to_numpy()
    df = pd.DataFrame({"symbol": list(panel.syms), "sig63": panel.sig63[i, :], "dv63": panel.dv63[i, :],
                       "price_usd": last_close, "market": panel.market})
    df = df[df.symbol.isin(oper) & np.isfinite(df.sig63) & (df.dv63.fillna(0) >= liq_floor)
            & (df.price_usd.fillna(0) >= 1.0)]
    if only is not None:
        df = df[df.symbol.isin(only)]
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
    df = df.sort_values("sig63", ascending=False, kind="mergesort").head(top * 3)
    df["max_abs_logret63"] = [max_abs_logret(panel, panel.col[s], i) for s in df.symbol]
    jump = df[df.max_abs_logret63 >= JUMP_LOG].copy()
    jump["refusal"] = [f"REFUSED_JUMP_X2 (one-day move x{np.exp(v):.1f} inside 63 sessions: split / spin / "
                       f"stitch / bad print)" for v in jump.max_abs_logret63]
    df = df[df.max_abs_logret63 < JUMP_LOG]
    return df.head(top).reset_index(drop=True), jump.reset_index(drop=True)


def _own_logrets(panel: Any, j: int, i: int, n: int = 63) -> np.ndarray:
    c = panel.close[: i + 1, j]
    c = c[np.isfinite(c) & (c > 0)][-(n + 1):]
    return np.diff(np.log(c.astype(float))) if len(c) > 1 else np.array([])


def max_abs_logret(panel: Any, j: int, i: int, n: int = 63) -> float:
    r = _own_logrets(panel, j, i, n)
    return float(np.max(np.abs(r))) if len(r) else float("nan")


def evt_symbols(cal_dir: Optional[Path] = None, *, window: tuple = EVT_WINDOW) -> tuple[set, str]:
    """MAXTAIL_EVT's event filter: US names with a vendor-announced or exchange-confirmed print in the
    contest window, from the latest contest calendar file. Returns (symbols, calendar file name)."""
    cal_dir = Path(cal_dir) if cal_dir is not None else cc.CAL_DIR
    files = sorted(cal_dir.glob("calendar_*.parquet"))
    if not files:
        return set(), "NONE"
    c = pd.read_parquet(files[-1], columns=["symbol", "date", "status", "market"])
    dd = pd.to_datetime(c.date)
    m = (c.market == "US") & c.status.isin(EVT_STATUSES) & (dd >= pd.Timestamp(window[0])) \
        & (dd <= pd.Timestamp(window[1]))
    return set(c.loc[m, "symbol"]), files[-1].name


# ───────────────────────────── the BOOK file (owner, by hand) ─────────────────────────────

def read_book_file(path: Path) -> tuple[Optional[str], Optional[str]]:
    """(book, None) or (None, reason). Tolerates a UTF-8 BOM, UTF-16 (PowerShell `echo >`), blank
    lines and stray whitespace. Absent file -> ('ROT5_TRAIL', None)."""
    p = Path(path)
    if not p.exists():
        return "ROT5_TRAIL", None
    try:
        raw = p.read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            txt = raw.decode("utf-16")
        elif len(raw) >= 2 and raw[1:2] == b"\x00":
            txt = raw.decode("utf-16-le")
        else:
            txt = raw.decode("utf-8-sig")
    except Exception as exc:                                   # noqa: BLE001
        return None, f"contest/live/BOOK unreadable ({type(exc).__name__}: {exc})"
    words = txt.replace("﻿", "").replace("\x00", "").split()
    if not words:
        return None, "contest/live/BOOK is empty"
    name = words[0].strip().upper()
    if name not in BOOKS_LIVE:
        return None, f"contest/live/BOOK names {name!r}; allowed: {', '.join(BOOKS_LIVE)}"
    return name, None


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

WLS_MIN_ROWS = 1000


def wls_export_check(folder: Path) -> tuple[bool, str, dict]:
    """A WLS membership export, not any ticker-like file: the newest CSV/Excel in `folder` must name
    WLS (file name or its header rows), carry a ticker column the loader finds, and hold >= 1,000
    member rows (WLS has roughly 10,000). Returns (ok, reason, info)."""
    folder = Path(folder)
    files = sorted([p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".xlsx", ".xls")],
                   key=lambda p: p.stat().st_mtime) if folder.exists() else []
    if not files:
        return False, "no WLS membership (MEMB) export in contest/wls/ (owner decision D1)", {}
    f = files[-1]
    info: dict = {"file": f.name}
    try:
        w = cc.load_wls_export(folder)
    except Exception as exc:                                   # noqa: BLE001
        return False, f"WLS export {f.name} is unreadable: {type(exc).__name__}: {exc}", info
    n = 0 if w is None else int(len(w))
    info["rows"] = n
    try:
        if f.suffix.lower() == ".csv":
            head = f.read_text(encoding="utf-8-sig", errors="replace")[:4000]
        else:
            h = pd.read_excel(f, header=None, nrows=8)
            head = " ".join(str(x) for x in h.to_numpy().ravel()) + " " + " ".join(str(c) for c in h.columns)
    except Exception:                                          # noqa: BLE001
        head = ""
    names_wls = "WLS" in f.name.upper() or "WLS" in head.upper()
    info["names_wls"] = names_wls
    if not names_wls:
        return False, f"WLS export {f.name}: neither its name nor its header rows say WLS (another index's MEMB?)", info
    if n < WLS_MIN_ROWS:
        return False, f"WLS export {f.name}: {n} member rows < {WLS_MIN_ROWS} (partial export?)", info
    return True, "", info


def live_gate(contest_dir: Optional[Path] = None) -> tuple[bool, list[str]]:
    """The live order sheet needs (D1) a WLS MEMB export in contest/wls/ that passes wls_export_check
    and (registration) the file contest/REGISTERED, created by hand by the owner."""
    contest_dir = Path(contest_dir) if contest_dir is not None else cc.CONTEST
    reasons = []
    ok, why, _ = wls_export_check(Path(contest_dir) / "wls")
    if not ok:
        reasons.append(why)
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
