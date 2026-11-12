"""CH-12: grade the news already acted on (ROADMAP CH-12; evidence N01, N13).

Two read-only graders over ledgers that already exist, each writing one receipt:

  buys       The hack6 "news sleeve" buys (fleet_manager decisions, role=hack6,
             kind=buy, mode=LIVE) graded at 5 sessions, SPY-adjusted, costs
             charged, against K matched NON-news names drawn on the same entry
             date from the same band.
  forecasts  The rule-based news_digest insider / positioning / congress
             forecasts in predictions.jsonl, re-scored from the rows (Brier
             recomputed, climatology and declared-control references, skill,
             reliability, resolution, date-block MDE, forecast-before-window).

    python -m scripts.ch12_news_grade buys --fm-dir <fleet_manager dir> --digest-dir <digest dir>
        --bars <parquet> [--bars <parquet> ...] --universe <potential_universe jsonl> --out DIR
        [--role hack6] [--before 2026-11-01] [--k 50] [--seed 20261112]
    python -m scripts.ch12_news_grade forecasts --predictions <predictions.jsonl>
        --bars <parquet> [--bars ...] --out DIR [--graded-by 2026-11-08]

Nothing is sent, no order is placed, no LLM is called, nothing under the inputs
is written: the receipt goes to `--out` only, which is REQUIRED (a default that
pointed into the runtime is how a "--no-write" run left a file in it, 11-11).
Exit 2 when the sample it was asked to grade cannot be located (CANNOT
DETERMINE is a red exit, not an empty receipt).

The verdict vocabulary is the scope-aware one (CLAUDE.md mission paragraph):
SUPPORTED_IN_SCOPE / CANNOT_DISTINGUISH / NOT_SUPPORTED_IN_SCOPE, each with its
t, its block count (n_effective counts date blocks, not rows), its MDE and one
sentence naming what it covers and what it does not. Exit 2 also when an input
is missing or `--out` points inside an input folder or any backend/data tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: 80% power at a two-sided 5% test: MDE = (1.96 + 0.84) x SE with many blocks;
#: with few blocks the t quantiles at df = n_blocks - 1 replace 1.96 and 0.84.
MDE_Z = 2.8
#: |t| beyond the two-sided 5% critical value (t at df = n_blocks - 1) decides.
VERDICT_Z = 2.0
VERDICTS = ("SUPPORTED_IN_SCOPE", "CANNOT_DISTINGUISH", "NOT_SUPPORTED_IN_SCOPE")
FAMILIES = ("news_digest:insider_v0", "news_digest:positioning_v0", "news_digest:congress_v0")
DEFAULT_SEED = 20261112
#: a control must not have been named by any digest stamped in the this-many
#: hours before the entry close (8 days: the 5-session hold plus a weekend)
NEWS_EXCLUSION_HOURS = 192.0

try:                                                            # the close is 16:00 New York
    from zoneinfo import ZoneInfo
    _NY: Any = ZoneInfo("America/New_York")
except Exception:                                               # noqa: BLE001 -- fixed-rule fallback below
    _NY = None


# ─────────────────────────────── small helpers ──────────────────────────────

def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_row(p: Path, *, newest: Optional[str] = None, newest_basis: str = "", glob: str = "*") -> dict:
    """Path, size, hash and the newest DATA date of one input (from the data's
    own stamps, never the filesystem mtime: a fresh checkout makes every file new)."""
    p = Path(p)
    if p.is_dir():
        files = sorted(x for x in p.glob(glob) if x.is_file())
        h = hashlib.sha256()
        for f in files:
            h.update(f.name.encode())
            h.update(sha256_of(f).encode())
        return {"path": str(p), "kind": "dir", "glob": glob, "n_files": len(files),
                "bytes": sum(f.stat().st_size for f in files), "sha256_of_member_hashes": h.hexdigest(),
                "newest_date": newest, "newest_basis": newest_basis}
    return {"path": str(p), "kind": "file", "bytes": p.stat().st_size, "sha256": sha256_of(p),
            "newest_date": newest, "newest_basis": newest_basis}


def stamp_of_name(name: str) -> Optional[str]:
    """`..._20261111T233002Z.json` -> '2026-11-11T23:30:02Z'; None when absent."""
    import re
    m = re.search(r"(\d{8}T\d{6}Z)", name)
    if not m:
        return None
    s = m.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}Z"


def newest_stamp_in_dir(d: Path, glob: str) -> Optional[str]:
    st = [stamp_of_name(f.name) for f in Path(d).glob(glob)]
    st = [s for s in st if s]
    return max(st) if st else None


def missing_inputs(paths: Sequence[Optional[Path]]) -> list[str]:
    return [str(p) for p in paths if p is not None and not Path(p).exists()]


def out_guard(out: Path, inputs: Sequence[Path]) -> Optional[str]:
    """Why `out` may not be written to, or None. Refuses any directory inside an
    input directory, inside the folder holding an input file, or under any
    `backend/data` tree (the runtime's live data)."""
    o = Path(out).resolve()
    parts = [x.lower() for x in o.parts]
    for i in range(len(parts) - 1):
        if parts[i] == "backend" and parts[i + 1] == "data":
            return f"--out {o} is under a backend/data tree (live data is read-only)"
    for p in inputs:
        p = Path(p).resolve()
        root = p if p.is_dir() else p.parent
        if o == root or root in o.parents:
            return f"--out {o} is inside the input folder {root}"
    return None


def count_files(folders: Sequence[Path]) -> dict[str, int]:
    """Files directly in each live folder (the BUILDER_RULES before/after count)."""
    out = {}
    for f in folders:
        f = Path(f)
        out[str(f)] = sum(1 for x in f.iterdir() if x.is_file()) if f.is_dir() else -1
    return out


def close_utc(d: date) -> datetime:
    """The 16:00 New York close of session `d`, in UTC."""
    if _NY is not None:
        return datetime.combine(d, time(16, 0), tzinfo=_NY).astimezone(timezone.utc)
    # fallback: US DST 2nd Sunday of March .. 1st Sunday of November
    mar = date(d.year, 3, 8 + (6 - date(d.year, 3, 8).weekday()) % 7)
    nov = date(d.year, 11, 1 + (6 - date(d.year, 11, 1).weekday()) % 7)
    hour = 20 if mar <= d < nov else 21
    return datetime.combine(d, time(hour, 0), tzinfo=timezone.utc)


def parse_ts(s: str) -> datetime:
    t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _r(x: Any, n: int = 6) -> Any:
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    return None if not math.isfinite(xf) else round(xf, n)


def block_se(values: Sequence[float], blocks: Sequence[Any]) -> dict:
    """SE of the mean with one observation per block (the block's mean).

    Rows inside a block share the block's news and market, so they are not
    independent; the honest n is the number of blocks."""
    by: dict[Any, list[float]] = defaultdict(list)
    for v, b in zip(values, blocks):
        if v is not None and math.isfinite(float(v)):
            by[b].append(float(v))
    means = np.array([np.mean(v) for v in by.values()], dtype=float)
    k = int(means.size)
    if k < 2:
        return {"n_blocks": k, "mean_of_blocks": _r(means.mean()) if k else None, "se": None}
    return {"n_blocks": k, "mean_of_blocks": _r(means.mean()),
            "se": _r(float(means.std(ddof=1) / math.sqrt(k)))}


def crit_values(n_blocks: Optional[int]) -> tuple[float, float]:
    """(two-sided 5% critical value, 80%-power quantile) for a mean over
    `n_blocks` independent blocks: Student t at df = n_blocks - 1, normal when
    scipy is absent or df is large."""
    df = (n_blocks or 0) - 1
    if df >= 1:
        try:
            from scipy import stats as _st
            return float(_st.t.ppf(0.975, df)), float(_st.t.ppf(0.80, df))
        except Exception:                                       # noqa: BLE001 -- normal fallback, stated in the rule
            pass
    return 1.959964, 0.841621


def mde_of(se: Optional[float], n_blocks: Optional[int]) -> Optional[float]:
    """Minimum detectable effect at 80% power, two-sided 5%, for this SE and block count."""
    if se is None or not math.isfinite(se) or se <= 0 or (n_blocks or 0) < 2:
        return None
    a, b = crit_values(n_blocks)
    return _r((a + b) * se)


def scoped_verdict(effect: Optional[float], se: Optional[float], *, n_blocks: Optional[int], covers: str,
                   does_not_cover: str, units: str, scope: str) -> dict:
    """One verdict word from VERDICTS, decided by a rule fixed before any number
    was read: SUPPORTED_IN_SCOPE when t > crit, NOT_SUPPORTED_IN_SCOPE when
    t < -crit, CANNOT_DISTINGUISH otherwise (including no SE). A verdict never
    leaves without its MDE: no SE means no MDE means CANNOT_DISTINGUISH."""
    crit, _pw = crit_values(n_blocks)
    mde = mde_of(se, n_blocks)
    t = (effect / se) if (effect is not None and se and math.isfinite(effect) and math.isfinite(se) and se > 0) else None
    if t is None or mde is None:
        label, why = "CANNOT_DISTINGUISH", "no standard error / MDE (fewer than two blocks or no rows)"
    elif t > crit:
        label, why = "SUPPORTED_IN_SCOPE", f"t {t:+.3g} > {crit:.3g} (df {n_blocks - 1}); effect {effect:+.4g}, MDE {mde:.4g}"
    elif t < -crit:
        label, why = "NOT_SUPPORTED_IN_SCOPE", f"t {t:+.3g} < -{crit:.3g} (df {n_blocks - 1}); effect {effect:+.4g}, MDE {mde:.4g}"
    else:
        label = "CANNOT_DISTINGUISH"
        why = (f"|t| {abs(t):.3g} <= {crit:.3g} (df {n_blocks - 1}); |effect| {abs(effect):.4g} vs MDE {mde:.4g}: "
               f"an effect smaller than the MDE would usually go unseen at this sample")
    assert label in VERDICTS
    return {"verdict": label, "scope_sentence": scope, "why": why, "effect": _r(effect), "se": _r(se),
            "t": _r(t, 3) if t is not None else None, "n_blocks": n_blocks, "mde_80pct_power": mde,
            "units": units, "covers": covers, "does_not_cover": does_not_cover,
            "rule": ("SUPPORTED_IN_SCOPE if t > t_crit, NOT_SUPPORTED_IN_SCOPE if t < -t_crit, else CANNOT_DISTINGUISH; "
                     "t_crit = Student t 0.975 at df = n_blocks - 1; SE from the coarser of the block schemes; "
                     "MDE = (t_0.975 + t_0.80) x SE at the same df (80% power, two-sided 5%)")}


# ─────────────────────────────── the bars panel ─────────────────────────────

def load_panel(paths: Sequence[Path], start: Optional[str] = None):
    """Long bars (symbol, date, close, volume, vwap) from one or more parquets;
    a LATER path wins a (symbol, date) clash, as in `one_event.load_closes`."""
    import pandas as pd
    frames = []
    for p in paths:
        filt = [("date", ">=", pd.Timestamp(start))] if start else None
        frames.append(pd.read_parquet(p, columns=["symbol", "date", "close", "volume", "vwap"],
                                      filters=filt))
    df = pd.concat(frames).drop_duplicates(["symbol", "date"], keep="last")
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def panel_audit(paths: Sequence[Path]) -> dict:
    """`xs_ranker.survivorship_audit` per bars file, plus the last date."""
    import pandas as pd
    from backend.services import xs_ranker as XR
    out = []
    for p in paths:
        b = pd.read_parquet(p, columns=["symbol", "date"])
        b["date"] = pd.to_datetime(b["date"])
        a = XR.survivorship_audit(b)
        last = b.groupby("symbol")["date"].max()
        sessions = sorted(b["date"].unique())
        cut = sessions[-22] if len(sessions) > 22 else sessions[0]
        a["stopped_more_than_21_sessions_before_end"] = int((last < cut).sum())
        a["path"] = str(p)
        out.append(a)
        del b
    return {"files": out}


class Panel:
    """Wide close / dollar-volume / vwap frames and the session calendar (SPY's)."""

    def __init__(self, long_df):
        self.close = long_df.pivot(index="date", columns="symbol", values="close").sort_index()
        dv = long_df.assign(dv=long_df["close"] * long_df["volume"])
        self.dv = dv.pivot(index="date", columns="symbol", values="dv").reindex(self.close.index)
        self.vwap = long_df.pivot(index="date", columns="symbol", values="vwap").reindex(self.close.index)
        if "SPY" not in self.close.columns:
            raise SystemExit("REFUSED: SPY is not in the bars panel; nothing can be SPY-adjusted")
        self.sessions: list[date] = [d for d in self.close.index if np.isfinite(self.close.at[d, "SPY"])]
        self.idx = {d: i for i, d in enumerate(self.sessions)}

    def entry_session(self, t: datetime) -> Optional[date]:
        """The first session whose close is strictly after `t`."""
        for d in self.sessions:
            if d >= t.date() and close_utc(d) > t:
                return d
        return None

    def offset(self, d: date, k: int) -> Optional[date]:
        i = self.idx.get(d)
        if i is None or i + k < 0 or i + k >= len(self.sessions):
            return None
        return self.sessions[i + k]

    def px(self, sym: str, d: Optional[date]) -> Optional[float]:
        if d is None or sym not in self.close.columns:
            return None
        v = self.close.at[d, sym]
        return float(v) if v is not None and np.isfinite(v) else None

    def features_before(self, d: date) -> "Any":
        """Cross-section known at the open of `d` (bars through d-1): 20-session
        median dollar volume, 63-session daily sigma, 5-session move in sigma."""
        import pandas as pd
        i = self.idx[d]
        if i < 64:
            raise SystemExit(f"REFUSED: fewer than 64 sessions of history before {d}")
        hist = self.close.loc[self.sessions[i - 64]:self.sessions[i - 1]]
        rets = hist.pct_change(fill_method=None).iloc[1:]
        sigma = rets.std(ddof=1)
        move5 = hist.iloc[-1] / hist.iloc[-6] - 1.0
        dvm = self.dv.loc[self.sessions[i - 20]:self.sessions[i - 1]].median()
        f = pd.DataFrame({"dv20": dvm, "sigma63": sigma,
                          "move5_sigma": move5 / (sigma * math.sqrt(5)),
                          "n_hist": rets.notna().sum()})
        return f


# ─────────────────────────────── Part A: the buys ───────────────────────────

def _run_files(fm_dir: Path) -> dict[str, Path]:
    out = {}
    for f in sorted((Path(fm_dir) / "runs").glob("run_*.json")):
        out[f.stem[len("run_"):]] = f
    return out


def attach_fills_and_triggers(buys: list[dict], fm_dir: Path, digest_dir: Path, *, role: str) -> dict:
    """Per buy: the fill (last action seen for its client order id), the digest
    the deciding run read, and the typed implication(s) that made the name a
    target. A name targeted on a day whose digest does not carry it (a top-up
    inside the 5-session hold) is traced to the most recent earlier digest that
    did, and labelled `carried`."""
    from backend.services import world_digest as WD
    runs = _run_files(fm_dir)
    acts: dict[str, dict] = {}
    run_digest: dict[str, str] = {}
    digest_seq: list[tuple[str, str]] = []          # (run started, digest file) for this role
    for rid, f in runs.items():
        d = json.loads(f.read_text(encoding="utf-8"))
        for a in d.get("accounts") or []:
            if a.get("role") != role:
                continue
            dg = (a.get("digest") or {}).get("file")
            if dg:
                run_digest[rid] = dg
                digest_seq.append((str(d.get("started_utc") or rid), dg))
            for x in a.get("actions") or []:
                if x.get("coid") and (x.get("entry_status") or x.get("filled_avg_price")):
                    acts[x["coid"]] = x
    cache: dict[str, dict] = {}

    def signal(name: str) -> tuple[dict, dict]:
        if name not in cache:
            p = Path(digest_dir) / name
            if not p.exists():
                cache[name] = ({}, {})
            else:
                dj = json.loads(p.read_text(encoding="utf-8"))
                imps, theme_of = [], {}
                for th in dj.get("themes") or []:
                    for i in th.get("implications") or []:
                        imps.append(i)
                        if i.get("subject_type") == "ticker":
                            theme_of.setdefault(i.get("subject"), []).append(
                                {"theme": str(th.get("title") or "")[:140], "direction": i.get("direction"),
                                 "confidence": i.get("confidence"), "horizon": i.get("horizon_sessions"),
                                 "size_bucket": i.get("size_bucket")})
                cache[name] = (WD.news_signal(imps), theme_of)
        return cache[name]

    missing_digest = 0
    for b in buys:
        fx = acts.get(b["coid"]) or {}
        b["fill_status"] = fx.get("entry_status")
        try:
            b["fill_price"] = float(fx["filled_avg_price"]) if fx.get("filled_avg_price") else None
        except (TypeError, ValueError):
            b["fill_price"] = None
        b["held_before"] = float((b.get("inputs") or {}).get("held_plus_pending") or 0.0)
        b["entry_kind"] = "new_entry" if b["held_before"] <= 0 else "top_up"
        dg = run_digest.get(b["run_id"])
        b["digest_file"] = dg
        trig = None
        if dg:
            sig, th = signal(dg)
            if b["symbol"] in sig and sig[b["symbol"]]["d"] > 0:
                trig = {"kind": "same_run", "digest": dg, **sig[b["symbol"]],
                        "implications": th.get(b["symbol"], [])[:4]}
        if trig is None:
            # most recent earlier digest (at most 10 days back) that carried the name
            t0 = parse_ts(b["t"])
            for started, name in sorted(digest_seq, reverse=True):
                try:
                    ts = parse_ts(started)
                except ValueError:
                    continue
                if ts > t0 or (t0 - ts).days > 10:
                    continue
                sig, th = signal(name)
                if b["symbol"] in sig and sig[b["symbol"]]["d"] > 0:
                    trig = {"kind": "carried", "digest": name, **sig[b["symbol"]],
                            "implications": th.get(b["symbol"], [])[:4]}
                    break
        if trig is None:
            missing_digest += 1
            trig = {"kind": "NOT_FOUND"}
        b["trigger"] = trig
    return {"n_with_fill_record": sum(1 for b in buys if b["fill_status"]),
            "n_filled": sum(1 for b in buys if b["fill_status"] == "filled" and b["fill_price"]),
            "n_trigger_not_found": missing_digest,
            "trigger_kinds": dict(Counter(b["trigger"]["kind"] for b in buys))}


def news_tickers_by_session(digest_dir: Path, sessions: Iterable[date], *,
                            hours: float = NEWS_EXCLUSION_HOURS) -> dict:
    """Every ticker any typed implication named in a world digest stamped in
    [close(d) - hours, close(d)) -- the names that had a news trigger available
    on session d or during the hold before it. Controls are drawn from outside
    this set."""
    stamps = []
    for p in sorted(Path(digest_dir).glob("world_digest_*.json")):
        try:
            ts = datetime.strptime(p.stem.split("_")[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        stamps.append((ts, p))
    tick_of: dict[Path, set[str]] = {}
    out: dict[date, set[str]] = {}
    for d in sessions:
        hi = close_utc(d)
        lo = hi - timedelta(hours=hours)
        names: set[str] = set()
        for ts, p in stamps:
            if lo <= ts < hi:
                if p not in tick_of:
                    dj = json.loads(p.read_text(encoding="utf-8"))
                    tick_of[p] = {str(i.get("subject")).upper() for th in dj.get("themes") or []
                                  for i in th.get("implications") or [] if i.get("subject_type") == "ticker"}
                names |= tick_of[p]
        out[d] = names
    return out


def load_sector_map(path: Optional[Path]) -> dict[str, str]:
    if not path or not Path(path).exists():
        return {}
    m = {}
    with Path(path).open(encoding="utf-8") as fh:
        for l in fh:
            if not l.strip():
                continue
            r = json.loads(l)
            s = (r.get("identity") or {}).get("sector")
            if s and r.get("symbol"):
                m[str(r["symbol"]).upper()] = s
    return m


def _qbucket(series, q: int):
    import pandas as pd
    return pd.qcut(series.rank(method="first"), q, labels=False)


def draw_controls(feat, *, sym: str, sector_of: dict[str, str], excluded: set[str], k: int,
                  rng: np.random.Generator, no_chase: Optional[float]) -> tuple[list[str], str, int]:
    """K names from the buy's band, the first tier that holds >= k names:
    sector x dollar-volume quintile; sector x dollar-volume tercile (both only
    when the buy has a sector); dollar-volume quintile x 63-session-vol tercile;
    dollar-volume quintile alone."""
    f = feat.dropna(subset=["dv20", "sigma63"]).copy()
    f = f[(f["dv20"] > 0) & (f["n_hist"] >= 40)]
    if sym not in f.index:
        return [], "BUY_HAS_NO_FEATURES", 0
    f["dvq"] = _qbucket(f["dv20"], 5)
    f["dvt"] = _qbucket(f["dv20"], 3)
    f["volq"] = _qbucket(f["sigma63"], 3)
    me = f.loc[sym]
    pool = f[~f.index.isin(excluded) & (f.index != sym) & (f.index != "SPY")]
    if no_chase is not None:
        pool = pool[pool["move5_sigma"].fillna(0) <= no_chase]
    tries = []
    sec = sector_of.get(sym)
    if sec:
        secs = pool.index.map(lambda s: sector_of.get(s))
        tries.append(("sector x dv quintile", pool[(secs == sec) & (pool["dvq"] == me["dvq"])]))
        tries.append(("sector x dv tercile", pool[(secs == sec) & (pool["dvt"] == me["dvt"])]))
    tries.append(("dv quintile x vol tercile", pool[(pool["dvq"] == me["dvq"]) & (pool["volq"] == me["volq"])]))
    tries.append(("dv quintile", pool[pool["dvq"] == me["dvq"]]))
    for name, cand in tries:
        if len(cand) >= k:
            pick = rng.choice(np.array(sorted(cand.index)), size=k, replace=False)
            return [str(x) for x in pick], name, int(len(cand))
    name, cand = tries[-1]
    return [str(x) for x in sorted(cand.index)], name + " (pool < k: all taken)", int(len(cand))


def leg(panel: Panel, sym: str, d0: date, h: int, entry_px: Optional[float] = None,
        spy_entry: Optional[float] = None) -> Optional[tuple[float, float]]:
    """(raw return of `sym`, raw return of SPY) from entry d0 to the close h
    sessions later, both gross; None when a bar is missing."""
    d1 = panel.offset(d0, h)
    p0 = entry_px if entry_px is not None else panel.px(sym, d0)
    p1 = panel.px(sym, d1)
    s0 = spy_entry if spy_entry is not None else panel.px("SPY", d0)
    s1 = panel.px("SPY", d1)
    if None in (p0, p1, s0, s1) or not p0 or not s0:
        return None
    return (p1 / p0 - 1.0), (s1 / s0 - 1.0)


def excess(panel: Panel, sym: str, d0: date, h: int, cost_rt: float,
           entry_px: Optional[float] = None, spy_entry: Optional[float] = None) -> Optional[float]:
    """Return net of `cost_rt` minus SPY's gross return over the same closes."""
    g = leg(panel, sym, d0, h, entry_px, spy_entry)
    return None if g is None else g[0] - g[1] - cost_rt


def grade_buys(buys: list[dict], panel: Panel, *, news_by_session: dict, sector_of: dict, k: int,
               seed: int, h: int, cost_rt: float, no_chase: Optional[float], use_fill: bool) -> tuple[list[dict], dict]:
    """One unit per buy: the buy's h-session return (raw, net, SPY-adjusted) and
    the mean of K band-matched controls' over the SAME closes. A control is
    never a name with a news trigger in the exclusion window, never a name the
    account bought within +-h sessions, never the buy itself and never SPY;
    `controls_sharing_event_name` counts violations and a violation refuses."""
    units, skipped = [], Counter()
    feats: dict[date, Any] = {}
    for b in buys:
        b["_entry"] = panel.entry_session(parse_ts(b["t"]))
    bought_idx: list[tuple[int, str]] = [(panel.idx[b["_entry"]], b["symbol"]) for b in buys if b["_entry"]]
    ctrl_dead = 0
    shared = 0
    for b in buys:
        d0 = b["_entry"]
        if d0 is None or panel.offset(d0, h) is None:
            skipped[f"PENDING: no bar {h} sessions after entry"] += 1
            continue
        entry_px = spy_px = None
        if use_fill:
            if not b.get("fill_price"):
                skipped["NO_FILL"] += 1
                continue
            entry_px = b["fill_price"]
            v = panel.vwap.at[d0, "SPY"] if "SPY" in panel.vwap.columns else None
            spy_px = float(v) if v is not None and np.isfinite(v) else None
        g = leg(panel, b["symbol"], d0, h, entry_px, spy_px)
        if g is None:
            skipped["NO_BARS_FOR_BUY"] += 1
            continue
        ex = g[0] - g[1] - cost_rt
        if d0 not in feats:
            feats[d0] = panel.features_before(d0)
        i0 = panel.idx[d0]
        held_near = {s for (i, s) in bought_idx if abs(i - i0) <= h}
        excl = set(news_by_session.get(d0, set())) | held_near
        rng = np.random.default_rng([seed, int(hashlib.sha256(b["coid"].encode()).hexdigest()[:12], 16)])
        ctrls, band, pool_n = draw_controls(feats[d0], sym=b["symbol"], sector_of=sector_of, excluded=excl,
                                            k=k, rng=rng, no_chase=no_chase)
        shared += sum(1 for c in ctrls if c in excl or c == b["symbol"] or c == "SPY")
        cx, craw = [], []
        for c in ctrls:
            gc = leg(panel, c, d0, h)
            if gc is None:
                ctrl_dead += 1
                continue
            cx.append(gc[0] - gc[1] - cost_rt)
            craw.append(gc[0])
        if len(cx) < min(20, k):
            skipped[f"FEWER_THAN_20_CONTROLS ({band})"] += 1
            continue
        cx_a = np.array(cx)
        pct = float((np.sum(cx_a < ex) + 0.5 * np.sum(cx_a == ex)) / cx_a.size)
        units.append({"coid": b["coid"], "symbol": b["symbol"], "decided_utc": b["t"], "entry": str(d0),
                      "exit": str(panel.offset(d0, h)), "month": str(d0)[:7],
                      "block5": i0 // h, "entry_kind": b.get("entry_kind"),
                      "entry_basis": "fill price; SPY at its session VWAP" if use_fill else "close of entry session",
                      "raw_news": g[0], "raw_spy": g[1], "raw_ctrl_mean": float(np.mean(craw)),
                      "excess_news": ex, "excess_ctrl_mean": float(cx_a.mean()),
                      "excess_ctrl_median": float(np.median(cx_a)), "d": ex - float(cx_a.mean()),
                      "pct_in_controls": pct, "n_controls": int(cx_a.size), "band": band, "band_pool": pool_n,
                      "sector": sector_of.get(b["symbol"]), "fill_status": b.get("fill_status"),
                      "trigger": {kk: (b.get("trigger") or {}).get(kk) for kk in ("kind", "digest", "d", "n")},
                      "themes": [i.get("theme") for i in (b.get("trigger") or {}).get("implications") or []][:3]})
    if shared:
        raise SystemExit(f"REFUSED: {shared} control draws share an event name (news-named, bought, or the buy itself)")
    return units, {"skipped": dict(skipped), "control_draws_without_exit_bar": ctrl_dead,
                   "controls_sharing_event_name": shared}


def coarser(*schemes: dict) -> dict:
    """Of several block_se results, the one with the LARGER SE (the coarser
    information count), with its block count: that pair sets t, df and MDE."""
    ok = [x for x in schemes if x.get("se") is not None]
    if not ok:
        return {"se": None, "n_blocks": max((x.get("n_blocks") or 0) for x in schemes) if schemes else 0}
    return max(ok, key=lambda x: x["se"])


def leave_one_out(values: Sequence[float], keys: Sequence[Any]) -> dict:
    """Mean of `values` with each key's rows left out, plus min / max and how
    many leave-outs flip the sign of the full mean."""
    ks = sorted({str(k) for k in keys})
    out = {}
    for k in ks:
        rest = [v for v, kk in zip(values, keys) if str(kk) != k]
        out[k] = _r(float(np.mean(rest))) if rest else None
    vals = [v for v in out.values() if v is not None]
    full = float(np.mean(values)) if len(values) else 0.0
    return {"by_left_out": out, "min": _r(min(vals)) if vals else None, "max": _r(max(vals)) if vals else None,
            "n_sign_flips": int(sum(1 for v in vals if np.sign(v) != np.sign(full)))}


def tail_check(values: Sequence[float], labels: Sequence[Any]) -> dict:
    """Share of the summed result carried by the top 5 rows (largest
    contributions in the direction of the total) and by the 5 largest |rows|."""
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return {"n": 0}
    tot = float(v.sum())
    sgn = 1.0 if tot >= 0 else -1.0
    top = np.argsort(-sgn * v)[:5]
    abs_tot = float(np.abs(v).sum())
    return {"n": int(v.size), "total_sum": _r(tot), "direction_of_total": "positive" if sgn > 0 else "negative",
            "top5_in_direction_of_total": [{"row": labels[i], "value": _r(float(v[i]))} for i in top],
            "top5_sum": _r(float(v[top].sum())),
            "top5_share_of_total": _r(float(v[top].sum()) / tot) if abs(tot) > 1e-12 else None,
            "top5_abs_share_of_sum_abs": _r(float(np.sort(np.abs(v))[-5:].sum()) / abs_tot) if abs_tot else None,
            "mean_without_top5": _r(float(np.delete(v, top).mean())) if v.size > 5 else None}


def summarise_units(units: list[dict], *, h: int) -> dict:
    if not units:
        return {"n": 0}
    d = np.array([u["d"] for u in units])
    exn = np.array([u["excess_news"] for u in units])
    exc = np.array([u["excess_ctrl_mean"] for u in units])
    pct = np.array([u["pct_in_controls"] for u in units])
    se_date = block_se(d, [u["entry"] for u in units])
    se_wk = block_se(d, [u["block5"] for u in units])
    used = coarser(se_date, se_wk)
    se_used, nb = used.get("se"), used.get("n_blocks")
    by_month = {}
    for m in sorted({u["month"] for u in units}):
        um = [u for u in units if u["month"] == m]
        by_month[m] = {"n": len(um), "n_dates": len({u["entry"] for u in um}),
                       "n_5_session_blocks": len({u["block5"] for u in um}),
                       "mean_raw_news": _r(np.mean([u["raw_news"] for u in um])),
                       "mean_raw_controls": _r(np.mean([u["raw_ctrl_mean"] for u in um])),
                       "mean_excess_news": _r(np.mean([u["excess_news"] for u in um])),
                       "mean_excess_controls": _r(np.mean([u["excess_ctrl_mean"] for u in um])),
                       "mean_d": _r(np.mean([u["d"] for u in um]))}
    dates = sorted({u["entry"] for u in units})
    by_date = {dt: {"n": sum(1 for u in units if u["entry"] == dt),
                    "mean_d": _r(np.mean([u["d"] for u in units if u["entry"] == dt]))} for dt in dates}
    hist, _ = np.histogram(pct, bins=10, range=(0.0, 1.0))
    pct_se = block_se(pct, [u["block5"] for u in units])
    trim = np.sort(d)[max(1, int(0.05 * d.size)):-max(1, int(0.05 * d.size))] if d.size >= 20 else d
    t = float(d.mean() / se_used) if se_used else None
    return {
        "n": int(d.size), "n_entry_dates": len(dates), "n_nonoverlapping_5_session_blocks": se_wk["n_blocks"],
        "n_effective_blocks_used": nb,
        "lines": {
            "raw_news_mean": _r(float(np.mean([u["raw_news"] for u in units]))),
            "raw_controls_mean": _r(float(np.mean([u["raw_ctrl_mean"] for u in units]))),
            "raw_spy_mean": _r(float(np.mean([u["raw_spy"] for u in units]))),
            "excess_news_vs_spy_net_mean": _r(exn.mean()),
            "excess_controls_vs_spy_net_mean": _r(exc.mean()),
            "d_news_minus_controls_mean": _r(d.mean()),
            "note": ("raw = gross price return over the hold; excess = raw - round-trip cost - SPY raw; "
                     "d = excess of the buy - mean excess of its own controls (the cost cancels in d)")},
        "mean_excess_news": _r(exn.mean()), "median_excess_news": _r(np.median(exn)),
        "mean_excess_controls": _r(exc.mean()), "median_excess_controls": _r(np.median(exc)),
        "mean_d_news_minus_controls": _r(d.mean()), "median_d": _r(np.median(d)),
        "trimmed_mean_d_5pct_each_tail": _r(trim.mean()),
        "share_d_positive": _r(float((d > 0).mean())),
        "se_by_entry_date": se_date, "se_by_5_session_block": se_wk, "se_used": _r(se_used),
        "t_vs_se_used": _r(t, 3) if t is not None else None,
        "mde_80pct_power": mde_of(se_used, nb),
        "by_month": by_month,
        "leave_one_month_out_mean_d": leave_one_out(list(d), [u["month"] for u in units]),
        "leave_one_5_session_block_out_mean_d": leave_one_out(list(d), [u["block5"] for u in units]),
        "leave_one_date_out_mean_d": leave_one_out(list(d), [u["entry"] for u in units]),
        "by_entry_date": by_date,
        "tail": tail_check(list(d), [f"{u['symbol']}@{u['entry']}" for u in units]),
        "percentile_in_own_controls": {
            "mean": _r(pct.mean()), "median": _r(np.median(pct)), "se_by_5_session_block": pct_se["se"],
            "deciles_counts": [int(x) for x in hist],
            "note": ("uniform on [0,1] (mean 0.5, ~n/10 per decile) means the news trigger carried no information "
                     "beyond its band at this horizon")},
    }


def load_news_buys(fm_dir: Path, *, role: str, before: Optional[str],
                   ledger: Optional[dict] = None) -> list[dict]:
    """LIVE, unrefused `kind=buy` decision rows of `role` with session < `before`.
    `ledger` (when given) receives the count at every filter, so each row the
    file holds and the sample does not is accounted for."""
    text = (Path(fm_dir) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    rows, bad = [], 0
    for l in text:
        if not l.strip():
            continue
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            bad += 1
    steps = [("role", lambda r: r.get("role") == role), ("row=decision", lambda r: r.get("row") == "decision"),
             ("kind=buy", lambda r: r.get("kind") == "buy"), ("mode=LIVE", lambda r: r.get("mode") == "LIVE"),
             ("not refused", lambda r: not r.get("refused")),
             (f"session < {before}", lambda r: before is None or str(r.get("session")) < before)]
    cur = rows
    led = {"rows_in_file": len(rows), "unparseable_lines": bad}
    for name, fn in steps:
        cur = [r for r in cur if fn(r)]
        led[f"after {name}"] = len(cur)
    if ledger is not None:
        ledger.update(led)
    return sorted(cur, key=lambda r: (r["t"], r["symbol"]))


def run_buys(a) -> int:
    from backend.services import world_digest as WD  # noqa: F401  -- fails loud if the signal rule moved
    out = Path(a.out)
    fm = Path(a.fm_dir)
    bars = [Path(p) for p in a.bars]
    need = [fm / "decisions.jsonl", fm / "runs", Path(a.digest_dir)] + bars + ([Path(a.universe)] if a.universe else [])
    miss = missing_inputs(need)
    if miss:
        print(f"CANNOT DETERMINE: missing input(s): {miss}")
        return 2
    why = out_guard(out, need)
    if why:
        print(f"REFUSED: {why}")
        return 2
    live_folders = sorted({str(p if p.is_dir() else p.parent) for p in need})
    before_counts = count_files([Path(x) for x in live_folders])
    out.mkdir(parents=True, exist_ok=True)
    ledger: dict = {}
    all_live = load_news_buys(fm, role=a.role, before=None)
    buys = load_news_buys(fm, role=a.role, before=a.before, ledger=ledger)
    if not buys:
        print(f"CANNOT DETERMINE: no LIVE {a.role} buy decisions before {a.before} in {fm / 'decisions.jsonl'}")
        return 2
    meta = attach_fills_and_triggers(buys, fm, Path(a.digest_dir), role=a.role)
    long_df = load_panel(bars, start=a.panel_start)
    panel = Panel(long_df)
    del long_df
    sessions = sorted({panel.entry_session(parse_ts(b["t"])) for b in buys} - {None})
    news_by = news_tickers_by_session(Path(a.digest_dir), sessions, hours=a.exclusion_hours)
    news_by_60 = news_tickers_by_session(Path(a.digest_dir), sessions, hours=60.0)
    sector_of = load_sector_map(Path(a.universe) if a.universe else None)
    cost_rt = 2.0 * a.cost_bps_side / 1e4
    common = dict(sector_of=sector_of, k=a.k, seed=a.seed, h=a.h, cost_rt=cost_rt)
    variants = {
        "V1_primary_all_buys_close_entry": dict(no_chase=2.0, use_fill=False, news=news_by, sel=lambda b: True),
        "V2_new_entries_only": dict(no_chase=2.0, use_fill=False, news=news_by,
                                    sel=lambda b: b["entry_kind"] == "new_entry"),
        "V3_filled_from_fill_price": dict(no_chase=2.0, use_fill=True, news=news_by, sel=lambda b: True),
        "V4_controls_without_no_chase_filter": dict(no_chase=None, use_fill=False, news=news_by, sel=lambda b: True),
        "V5_news_exclusion_60h_as_dev1": dict(no_chase=2.0, use_fill=False, news=news_by_60, sel=lambda b: True),
    }
    res, units_primary = {}, []
    for name, v in variants.items():
        sel = [b for b in buys if v["sel"](b)]
        units, info = grade_buys(sel, panel, news_by_session=v["news"], no_chase=v["no_chase"],
                                 use_fill=v["use_fill"], **common)
        res[name] = {"n_selected": len(sel), **info, "summary": summarise_units(units, h=a.h)}
        if name.startswith("V1"):
            units_primary = units
    p = res["V1_primary_all_buys_close_entry"]["summary"]
    if not p.get("n"):
        print(f"CANNOT DETERMINE: none of {len(buys)} buys could be graded: {res['V1_primary_all_buys_close_entry']['skipped']}")
        return 2
    skipped = res["V1_primary_all_buys_close_entry"]["skipped"]
    if p.get("n", 0) + sum(skipped.values()) != len(buys):
        raise SystemExit(f"REFUSED: graded {p.get('n')} + skipped {sum(skipped.values())} != sample {len(buys)}")
    covers = (f"{a.role}'s LIVE news-sleeve buy decisions (contract hack6_v2) with session before {a.before}: "
              f"{p.get('n')} buys on {p.get('n_entry_dates')} entry dates ({p.get('n_nonoverlapping_5_session_blocks')} "
              f"non-overlapping {a.h}-session blocks), graded {a.h} sessions close-to-close, SPY-adjusted, "
              f"{a.cost_bps_side:g} bps per side, each against {a.k} band-matched names with no news trigger")
    nb = p.get("n_effective_blocks_used")
    scope = (f"Over {p.get('n')} {a.role} news buys from {min(str(b['session']) for b in buys)} to "
             f"{max(str(b['session']) for b in buys)} ({nb} independent blocks), the {a.h}-session excess of the "
             f"bought names over same-band no-news names is {p.get('mean_d_news_minus_controls'):+.4f} "
             f"(MDE {p.get('mde_80pct_power')}); this says nothing about news as a mechanism, other horizons, "
             f"the account's stops, or the digest after typing resumed on 11-10.")
    verdict = scoped_verdict(p.get("mean_d_news_minus_controls"), p.get("se_used"), n_blocks=nb, covers=covers,
                             does_not_cover=("news as a mechanism in general; other horizons (20 sessions); the "
                                             "contract's 3-sigma stop (the grade is close-to-close, no stop); short "
                                             "or risk-off use of news; the digest after typing resumed (11-10 onward); "
                                             "a sized or ranked news book; any other account"),
                             units=f"{a.h}-session excess return, fraction (0.01 = 1%)", scope=scope)
    sess_counts = Counter(str(b["session"]) for b in all_live)
    after_counts = count_files([Path(x) for x in live_folders])
    dec_newest = max(str(r.get("t")) for r in all_live) if all_live else None
    inputs = [input_row(fm / "decisions.jsonl", newest=dec_newest, newest_basis=f"max t over LIVE {a.role} buy rows"),
              input_row(fm / "runs", glob="run_*.json", newest=newest_stamp_in_dir(fm / "runs", "run_*.json"),
                        newest_basis="run id stamp in the file name"),
              input_row(Path(a.digest_dir), glob="world_digest_*.json",
                        newest=newest_stamp_in_dir(Path(a.digest_dir), "world_digest_*.json"),
                        newest_basis="digest stamp in the file name")]
    audit = panel_audit(bars)
    for bp, au in zip(bars, audit["files"]):
        inputs.append(input_row(bp, newest=au.get("panel_last_session"), newest_basis="max bar date"))
    if a.universe:
        u = Path(a.universe)
        inputs.append(input_row(u, newest=u.stem, newest_basis="universe day in the file name"))
    receipt = {
        "schema": "ch12_news_grade/buys/2", "run_id": a.run_id,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "PRODUCT_EXPERIMENT (a grade of past paper decisions; no claim)",
        "question": (f"Did the names the {a.role} news sleeve bought beat names from the same band that had no news "
                     f"trigger, over the {a.h} sessions the contract holds them?"),
        "headline": {"verdict": verdict["verdict"], "scope_sentence": scope, "n": p.get("n"),
                     "n_entry_dates": p.get("n_entry_dates"), "n_effective_blocks": nb,
                     "raw_news_mean": p["lines"]["raw_news_mean"], "raw_controls_mean": p["lines"]["raw_controls_mean"],
                     "raw_spy_mean": p["lines"]["raw_spy_mean"],
                     "excess_news_vs_spy_net_mean": p["lines"]["excess_news_vs_spy_net_mean"],
                     "excess_controls_vs_spy_net_mean": p["lines"]["excess_controls_vs_spy_net_mean"],
                     "d_news_minus_controls_mean": p.get("mean_d_news_minus_controls"),
                     "se": p.get("se_used"), "t": p.get("t_vs_se_used"), "mde_80pct_power": p.get("mde_80pct_power"),
                     "top5_share_of_total": p["tail"].get("top5_share_of_total"),
                     "cost": f"{a.cost_bps_side:g} bps per side, {2 * a.cost_bps_side:g} bps round trip",
                     "variants_tried": len(variants)},
        "sample": {"rule": (f"decisions.jsonl rows with role={a.role}, row=decision, kind=buy, mode=LIVE, refused "
                            f"empty, session < {a.before}"),
                   "row_ledger": ledger,
                   "dropped_after_sample": {"graded": p.get("n"), **skipped},
                   "n": len(buys), "first_session": min(str(b['session']) for b in buys),
                   "last_session": max(str(b['session']) for b in buys),
                   "all_live_buys_any_date": len(all_live), "live_buys_by_session": dict(sorted(sess_counts.items())),
                   "excluded_by_cutoff_note": (f"{len(all_live) - len(buys)} LIVE buys on or after {a.before} are outside "
                                               f"the sample (the digest changed when typing resumed; their 5-session "
                                               f"windows may not have closed)"),
                   "entry_kinds": dict(Counter(b["entry_kind"] for b in buys)), **meta},
        "method": {"horizon_sessions": a.h,
                   "entry": ("close of the first session whose 16:00 ET close is after the decision timestamp "
                             "(V3: the recorded fill price, SPY at that session's VWAP)"),
                   "exit": f"close {a.h} sessions after the entry session", "benchmark": "SPY over the same closes",
                   "cost": (f"{a.cost_bps_side:g} bps per side ({2 * a.cost_bps_side:g} bps round trip), the hack6_v2 "
                            f"contract's costs.assumed_bps_per_side, charged to news and controls alike"),
                   "controls": {"k": a.k, "seed": a.seed, "rng": "np.random.default_rng([seed, sha256(coid)[:12]])",
                                "matched_on": ("first tier with >= k names: sector (potential_universe identity.sector) "
                                               "x 20-session median dollar-volume quintile; sector x dv tercile; "
                                               "dv quintile x 63-session daily-vol tercile; dv quintile alone. The "
                                               "receipt's units name the tier each buy used."),
                                "not_matched_on": "market cap, beta, momentum beyond the no-chase filter, earnings dates",
                                "eligibility": (f"in the panel with >= 40 of 63 sessions of history before entry; not named "
                                                f"by any typed ticker implication in any world digest stamped in the "
                                                f"{a.exclusion_hours:g} h before the entry close; not bought by {a.role} "
                                                f"within +-{a.h} sessions of the entry; not the buy; not SPY; V1-V3, V5 "
                                                f"also apply the contract's no-chase filter (5-session move <= 2 sigma)"),
                                "features_known_at": "bars through the session before entry"},
                   "percentile": "share of the buy's own controls with a lower excess (ties half)",
                   "blocks": ("SE of the mean of d with one observation per entry date and, separately, per "
                              "non-overlapping 5-session block (session index // 5); the coarser (larger) SE and its "
                              "block count set t, df and MDE"),
                   "variants_tried": list(variants),
                   "development_history": ("dev1 (2026-11-11, copies of the inputs) used a 60 h exclusion and z-based "
                                           "MDE; V5 reproduces its exclusion")},
        "panel": {**audit, "sessions_loaded_from": a.panel_start, "calendar_last_session": str(panel.sessions[-1])},
        "results": res, "verdict": verdict,
        "units_primary": [{k2: (_r(v2) if isinstance(v2, float) else v2) for k2, v2 in u.items()} for u in units_primary],
        "inputs": inputs,
        "live_folder_file_counts": {"before": before_counts, "after": after_counts,
                                    "note": "scheduled jobs write these folders; a change is theirs, this run writes only --out"},
        "claims_promoted": "none",
    }
    path = out / f"ch12_news_buys_{a.run_id}.json"
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print(f"live folder file counts before {before_counts}")
    print(f"live folder file counts after  {after_counts}")
    print(f"buys: n={len(buys)} graded={p.get('n')} dates={p.get('n_entry_dates')} blocks={nb} "
          f"raw news={p['lines']['raw_news_mean']} raw ctrl={p['lines']['raw_controls_mean']} "
          f"raw spy={p['lines']['raw_spy_mean']} excess news={p['lines']['excess_news_vs_spy_net_mean']} "
          f"excess ctrl={p['lines']['excess_controls_vs_spy_net_mean']} d={p.get('mean_d_news_minus_controls')} "
          f"se={p.get('se_used')} t={p.get('t_vs_se_used')} mde={p.get('mde_80pct_power')} -> {verdict['verdict']}")
    print(f"receipt {path}")
    return 0


# ─────────────────────────────── Part B: the forecasts ──────────────────────

def load_family_forecasts(path: Path, families: Sequence[str] = FAMILIES,
                          stats: Optional[dict] = None) -> list[dict]:
    """Stream the ledger read-only (it is large and rewritten in place, so a
    torn line is counted, not fatal). `stats` receives the line count, the
    unparseable count and the newest `made_at` over EVERY row."""
    import re
    out, n_lines, bad, newest = [], 0, 0, ""
    pat = re.compile(r'"made_at":\s*"([^"]+)"')
    with Path(path).open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            n_lines += 1
            m = pat.search(line)
            if m and m.group(1) > newest:
                newest = m.group(1)
            if "news_digest:" not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if r.get("specialist") in families:
                out.append(r)
    if stats is not None:
        stats.update(n_lines=n_lines, unparseable_family_lines=bad, newest_made_at=newest or None)
    return out


def forecast_window(rec: dict, sessions: Sequence[date]) -> dict:
    """The grader's window (`belief_state.resolution_start_date` -> the first bar
    on or after the made_at DATE) and how long before its entry close the row
    was written. A negative gap = the window started before the forecast."""
    made = parse_ts(rec["made_at"])
    start = made.date()
    entry = next((d for d in sessions if d >= start), None)
    if entry is None:
        return {"entry": None, "gap_h": None}
    gap = (close_utc(entry) - made).total_seconds() / 3600.0
    return {"entry": str(entry), "gap_h": gap}


def _skill_boot(p: np.ndarray, y: np.ndarray, ref: Optional[np.ndarray], blocks: Sequence[Any],
                rng: np.random.Generator, n_boot: int) -> dict:
    """Skill = 1 - BS/BS_ref with a block bootstrap SE. ref None -> the cell's
    own climatology (its base rate), recomputed inside every resample."""
    def skill(ix: np.ndarray) -> float:
        pp, yy = p[ix], y[ix]
        bs = float(np.mean((pp - yy) ** 2))
        if ref is None:
            base = float(yy.mean())
            bref = float(np.mean((base - yy) ** 2))
        else:
            bref = float(np.mean((ref[ix] - yy) ** 2))
        return 1.0 - bs / bref if bref > 0 else float("nan")
    by: dict[Any, list[int]] = defaultdict(list)
    for i, b in enumerate(blocks):
        by[b].append(i)
    keys = list(by)
    full = skill(np.arange(p.size))
    if len(keys) < 2:
        return {"skill": _r(full), "se": None, "n_blocks": len(keys)}
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), size=len(keys))
        ix = np.concatenate([np.array(by[keys[j]]) for j in pick])
        v = skill(ix)
        if math.isfinite(v):
            vals.append(v)
    se = float(np.std(vals, ddof=1)) if len(vals) > 1 else None
    return {"skill": _r(full), "se": _r(se), "n_blocks": len(keys)}


def _two_block_se(values: Sequence[float], rows: Sequence[dict]) -> dict:
    """Block SE of a mean two ways: forecast date, and non-overlapping horizon
    windows (h, entry session // h). Same-horizon windows that overlap share
    their returns, so the date count overstates the information; the coarser
    SE (and its block count) is the one a verdict reads."""
    d = block_se(values, [r["made_at"][:10] for r in rows])
    hz = block_se(values, [r.get("_hblock") for r in rows])
    used = coarser(d, hz)
    se, nb = used.get("se"), used.get("n_blocks")
    m = float(np.mean(values)) if len(values) else None
    return {"mean": _r(m), "se_date_blocks": d["se"],
            "n_date_blocks": d["n_blocks"], "se_horizon_blocks": hz["se"], "n_horizon_blocks": hz["n_blocks"],
            "se_used": _r(se), "n_blocks_used": nb, "t": _r(m / se, 3) if (se and m is not None) else None,
            "mde_80pct_power": mde_of(se, nb)}


def _declared_ref(rows: Sequence[dict]) -> np.ndarray:
    """The row's DECLARED control: a 0.5 coin for direction, the vol prior for size."""
    return np.array([float((r.get("inputs_used") or {}).get("vol_prior_p"))
                     if r["observable"] == "abs_move_exceeds"
                     and (r.get("inputs_used") or {}).get("vol_prior_p") is not None
                     else 0.5 for r in rows])


def score_cell(rows: list[dict], *, rng: np.random.Generator, n_boot: int, full: bool = True) -> dict:
    from backend.services import calibration as CAL
    if not rows:
        return {"n": 0}
    p = np.array([float(r["probability"]) for r in rows])
    y = np.array([float(r["outcome"]) for r in rows])
    dblocks = [r["made_at"][:10] for r in rows]
    hblocks = [r.get("_hblock") for r in rows]
    bs_i = (p - y) ** 2
    bs = float(bs_i.mean())
    base = float(y.mean())
    obs = {r["observable"] for r in rows}
    ref_decl = _declared_ref(rows)
    raw = np.array([float(r.get("raw_probability") if r.get("raw_probability") is not None else r["probability"])
                    for r in rows])

    def skill(pp: np.ndarray, ref: Optional[np.ndarray]) -> dict:
        a_ = _skill_boot(pp, y, ref, dblocks, rng, n_boot)
        b_ = _skill_boot(pp, y, ref, hblocks, rng, n_boot)
        used = coarser(a_, b_)
        se, nb = used.get("se"), used.get("n_blocks")
        sk = a_["skill"]
        return {"skill": sk, "se_date_blocks": a_["se"], "n_date_blocks": a_["n_blocks"],
                "se_horizon_blocks": b_["se"], "n_horizon_blocks": b_["n_blocks"],
                "se": _r(se), "n_blocks_used": nb,
                "t": _r(sk / se, 3) if (se and sk is not None) else None, "mde_80pct_power": mde_of(se, nb)}

    excess_brier = bs_i - (ref_decl - y) ** 2          # > 0: worse than the declared control on that row
    out: dict[str, Any] = {
        "n": int(p.size), "n_date_blocks": len(set(dblocks)), "n_horizon_blocks": len(set(hblocks)),
        "observables": sorted(obs),
        "brier": _r(bs), "base_rate": _r(base), "brier_climatology": _r(base * (1 - base)),
        "brier_const_0_5": 0.25, "brier_declared_control": _r(float(np.mean((ref_decl - y) ** 2))),
        "brier_minus_0_25": _r(bs - 0.25), "brier_minus_climatology": _r(bs - base * (1 - base)),
        "brier_raw_probability_before_shrink": _r(float(np.mean((raw - y) ** 2))),
        "p_distinct": sorted({_r(x, 4) for x in p})[:12], "p_min": _r(p.min()), "p_max": _r(p.max()),
        "skill_vs_declared_control": skill(p, ref_decl),
    }
    if not full:
        return out
    dec = CAL.brier_decomposition(p, y)
    out.update({
        "skill_vs_climatology": skill(p, None),
        "skill_raw_probability_vs_declared_control": skill(raw, ref_decl),
        "decomposition_murphy_bins": {k: (_r(v) if isinstance(v, float) else v) for k, v in dec.items() if k != "bins"},
        "reliability_resolution_by_stated_p": _rel_res(p, y),
        "reliability_by_stated_p": [
            {"p": _r(v, 4), "n": int((p == v).sum()), "mean_outcome": _r(float(y[p == v].mean()), 4),
             "outcome_se": _r(math.sqrt(max(y[p == v].mean() * (1 - y[p == v].mean()), 0) / max((p == v).sum(), 1)), 4)}
            for v in sorted(set(p.tolist()))],
        "leave_one_month_out_brier_minus_control": leave_one_out(list(excess_brier), [r["made_at"][:7] for r in rows]),
        "leave_one_horizon_block_out_brier_minus_control": leave_one_out(list(excess_brier), [str(b) for b in hblocks]),
        "tail_brier_minus_control": tail_check(list(excess_brier),
                                               [f"{r['ticker']}@{r['made_at'][:10]}" for r in rows]),
    })
    dirn = [r for r in rows if r["observable"] == "beats_benchmark" and float(r["probability"]) != 0.5]
    if dirn:
        sgn = {r["prediction_id"]: (1.0 if float(r["probability"]) > 0.5 else -1.0) for r in dirn}
        hit = [float((float(r["probability"]) > 0.5) == bool(r["outcome"])) for r in dirn]
        sg = [r for r in dirn if r.get("vs_benchmark") is not None]
        rw = [r for r in dirn if (r.get("resolution_detail") or {}).get("realised_return") is not None]
        signed = [sgn[r["prediction_id"]] * float(r["vs_benchmark"]) for r in sg]
        out["direction"] = {
            "n": len(dirn), "n_long": sum(1 for r in dirn if float(r["probability"]) > 0.5),
            "hit_rate": _two_block_se(hit, dirn),
            "raw_signed_return_gross": (_two_block_se([sgn[r["prediction_id"]] * float(r["resolution_detail"]["realised_return"])
                                                       for r in rw], rw) if rw else None),
            "signed_excess_vs_spy_gross": _two_block_se(signed, sg) if sg else None,
            "signed_excess_vs_spy_net_20bps_rt": _two_block_se([x - 0.002 for x in signed], sg) if sg else None,
            "note": ("signed by the forecast's side (p > 0.5 long, p < 0.5 short); raw = the stock's own return; "
                     "a forecast is not a trade, so the ledger charges no cost; the net line charges the 20 bps "
                     "round trip a traded version would pay")}
        pe = [r for r in dirn if r.get("_peer") is not None]
        if pe:
            out["direction"]["signed_excess_over_band_peers"] = {
                "n": len(pe), **_two_block_se([r["_peer"] for r in pe], pe),
                "mean_pct_in_peers": _r(float(np.mean([r["_peer_pct"] for r in pe]))),
                "note": ("the row's own return minus the mean of K band-matched names (same entry and exit closes, "
                         "not named by any of these families that day), signed by the forecast's side: "
                         "separates the rule from the band's beta vs SPY")}
    return out


def _rel_res(p: np.ndarray, y: np.ndarray) -> dict:
    """Murphy split over the DISTINCT stated probabilities (exact for a forecast
    with few values): BS = reliability - resolution + uncertainty."""
    n = p.size
    base = float(y.mean())
    rel = res = 0.0
    for v in set(p.tolist()):
        m = p == v
        ok = float(y[m].mean())
        rel += m.sum() * (v - ok) ** 2
        res += m.sum() * (ok - base) ** 2
    rel, res = rel / n, res / n
    unc = base * (1 - base)
    return {"reliability": _r(rel), "resolution": _r(res), "uncertainty": _r(unc),
            "brier_identity": _r(rel - res + unc), "brier_actual": _r(float(np.mean((p - y) ** 2))),
            "note": "reliability (lower is better) - resolution (higher is better) + uncertainty = Brier, exactly"}


def peer_check(rows: list[dict], bars: Sequence[Path], *, k: int, seed: int, panel_start: str) -> dict:
    """For each directional row whose ticker is in the panel: its own excess vs
    SPY minus the mean of K band-matched names' (same closes), signed by the
    forecast's side; written onto the row as `_peer` / `_peer_pct`."""
    dirn = [r for r in rows if r["observable"] == "beats_benchmark" and float(r["probability"]) != 0.5]
    if not dirn:
        return {"n": 0}
    long_df = load_panel(bars, start=panel_start)
    panel = Panel(long_df)
    del long_df
    named: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        named[r["made_at"][:10]].add(str(r["ticker"]).upper())
    feats: dict[date, Any] = {}
    why = Counter()
    shared = 0
    for r in dirn:
        d0 = date.fromisoformat(r["_win"]["entry"])
        h = int(r["horizon_days"])
        if d0 not in panel.idx or panel.offset(d0, h) is None:
            why["no_panel_window"] += 1
            continue
        ex = excess(panel, r["ticker"], d0, h, 0.0)
        if ex is None:
            why["ticker_not_in_panel"] += 1
            continue
        if d0 not in feats:
            feats[d0] = panel.features_before(d0)
        rng = np.random.default_rng([seed, int(hashlib.sha256(r["prediction_id"].encode()).hexdigest()[:12], 16)])
        excl = named[r["made_at"][:10]]
        ctrls, band, _n = draw_controls(feats[d0], sym=r["ticker"], sector_of={}, excluded=excl,
                                        k=k, rng=rng, no_chase=None)
        shared += sum(1 for c in ctrls if c in excl or c == r["ticker"])
        cx = [v for v in (excess(panel, c, d0, h, 0.0) for c in ctrls) if v is not None]
        if len(cx) < 20:
            why["fewer_than_20_peers"] += 1
            continue
        sgn = 1.0 if float(r["probability"]) > 0.5 else -1.0
        r["_peer"] = sgn * (ex - float(np.mean(cx)))
        cxa = np.array(cx)
        pct = float((np.sum(cxa < ex) + 0.5 * np.sum(cxa == ex)) / cxa.size)
        r["_peer_pct"] = pct if sgn > 0 else 1.0 - pct
        why["graded_vs_peers"] += 1
    if shared:
        raise SystemExit(f"REFUSED: {shared} peer draws share an event name")
    return {"k": k, "band": "dv quintile x 63-session-vol tercile (no sector tier: mostly small caps)",
            "peers_sharing_event_name": shared, **dict(why)}


def run_forecasts(a) -> int:
    import pandas as pd
    out = Path(a.out)
    pred = Path(a.predictions)
    bars = [Path(p) for p in a.bars]
    need = [pred] + bars
    miss = missing_inputs(need)
    if miss:
        print(f"CANNOT DETERMINE: missing input(s): {miss}")
        return 2
    why = out_guard(out, need)
    if why:
        print(f"REFUSED: {why}")
        return 2
    live_folders = sorted({str(p.parent) for p in need})
    before_counts = count_files([Path(x) for x in live_folders])
    out.mkdir(parents=True, exist_ok=True)
    stats: dict = {}
    rows = load_family_forecasts(pred, stats=stats)
    graded_all = [r for r in rows if r.get("outcome") is not None and not r.get("void_reason")]
    voided = [r for r in rows if r.get("void_reason")]
    pending = [r for r in rows if r.get("outcome") is None and not r.get("void_reason")]
    sample = [r for r in graded_all if a.graded_by is None or str(r.get("resolved_at"))[:10] <= a.graded_by]
    if not sample:
        print(f"CANNOT DETERMINE: no graded {FAMILIES} rows resolved by {a.graded_by} in {pred}")
        return 2
    mism = sum(1 for r in sample if abs((float(r["probability"]) - float(r["outcome"])) ** 2 - float(r["brier"])) > 1e-9)
    cal = pd.read_parquet(bars[0], columns=["symbol", "date"], filters=[("symbol", "==", "SPY")])
    sessions = sorted(pd.to_datetime(cal["date"]).dt.date.unique())
    if not sessions:
        print(f"CANNOT DETERMINE: SPY has no bars in {bars[0]}")
        return 2
    for r in graded_all:
        r["_win"] = forecast_window(r, sessions)
    late = [r for r in sample if r["_win"]["gap_h"] is not None and r["_win"]["gap_h"] <= 0]
    nowin = [r for r in sample if r["_win"]["gap_h"] is None]
    clean = [r for r in sample if r["_win"]["gap_h"] is not None and r["_win"]["gap_h"] > 0]
    gaps = np.array([r["_win"]["gap_h"] for r in sample if r["_win"]["gap_h"] is not None])
    sidx = {d: i for i, d in enumerate(sessions)}
    for r in graded_all:
        e = date.fromisoformat(r["_win"]["entry"]) if r["_win"].get("entry") else None
        r["_hblock"] = (int(r["horizon_days"]), sidx[e] // int(r["horizon_days"])) if e in sidx else None
    peer_info = peer_check(clean, bars, k=a.k, seed=a.seed, panel_start=a.panel_start)
    # re-grade from the bars with the ledger's own resolver, where the panel has the name
    from backend.services import belief_state as BS
    from backend.services import one_event as OE
    closes = OE.load_closes(bars, {r["ticker"] for r in clean})
    px = closes.copy()
    px.index = pd.to_datetime(px.index)
    regr = Counter()
    for r in clean:
        if r["ticker"] not in px.columns:
            regr["ticker_not_in_panel"] += 1
            continue
        rec = {k: v for k, v in r.items() if not k.startswith("_")}
        rec.update(outcome=None, brier=None, resolved_at=None)
        got = BS.resolve_one(rec, px, today=date.fromisoformat(str(r["resolved_at"])[:10]))
        if got is None:
            regr["not_gradeable_on_panel"] += 1
        else:
            regr["agree" if int(got["outcome"]) == int(r["outcome"]) else "disagree"] += 1
    rng = np.random.default_rng(a.seed)

    def cells(rs: list[dict]) -> dict:
        fam = {}
        for f in FAMILIES:
            x = [r for r in rs if r["specialist"] == f]
            fam[f] = {"all": score_cell(x, rng=rng, n_boot=a.n_boot)}
            for (obs, hz) in sorted({(r["observable"], r["horizon_days"]) for r in x}):
                fam[f][f"{obs}_h{hz}"] = score_cell([r for r in x if r["observable"] == obs and r["horizon_days"] == hz],
                                                    rng=rng, n_boot=a.n_boot)
            fam[f]["by_month"] = {m: score_cell([r for r in x if r["made_at"][:7] == m], rng=rng, n_boot=200, full=False)
                                  for m in sorted({r["made_at"][:7] for r in x})}
            fam[f]["by_rule"] = {ru: score_cell([r for r in x if (r.get("inputs_used") or {}).get("rule") == ru],
                                                rng=rng, n_boot=200, full=False)
                                 for ru in sorted({(r.get("inputs_used") or {}).get("rule") for r in x} - {None})}
        return fam

    res_clean = cells(clean)
    pooled = score_cell(clean, rng=rng, n_boot=a.n_boot)
    dnc = ("the underlying insider / short-interest / COT / congress data as a signal (the stated probabilities are "
           "shrunk x0.2 toward 0.5, so the Brier cannot move far from 0.25 by construction); other horizons; "
           "a traded book on these rules; rows resolved after the sample date")

    def fam_scope(name: str, c: dict, v_word_hint: str) -> str:
        sk = c.get("skill_vs_declared_control") or {}
        dr = c.get("direction") or {}
        pe = dr.get("signed_excess_over_band_peers") or {}
        tail = (f"; against band-matched peers the signed excess is {pe.get('mean'):+.4f} (MDE {pe.get('mde_80pct_power')})"
                if pe.get("mean") is not None else "")
        return (f"{name}: {c.get('n')} rows made before their window, {sk.get('n_blocks_used')} independent blocks, "
                f"Brier {c.get('brier')} vs 0.25 coin / {c.get('brier_declared_control')} declared control / "
                f"{c.get('brier_climatology')} climatology, skill {sk.get('skill')} (MDE {sk.get('mde_80pct_power')})"
                f"{tail}; this grades the stated probabilities over Sep-Oct 2026, not the underlying data as a "
                f"signal{v_word_hint}.")

    verdicts = {}
    for f in FAMILIES + ("pooled",):
        c = pooled if f == "pooled" else res_clean[f]["all"]
        sk = c.get("skill_vs_declared_control") or {}
        hint = ""
        if f == "news_digest:insider_v0":
            hint = (" (the Brier deficit tracks insider names lagging SPY, a band/beta effect the peer line "
                    "separates)")
        verdicts[f] = scoped_verdict(sk.get("skill"), sk.get("se"), n_blocks=sk.get("n_blocks_used"),
                                     covers=(f"{f}: {c.get('n')} graded rows made before their window, "
                                             f"{c.get('n_date_blocks')} forecast dates / {c.get('n_horizon_blocks')} "
                                             f"non-overlapping horizon windows, {', '.join(c.get('observables', []))}; "
                                             f"skill = 1 - Brier / Brier(declared control: 0.5 coin for direction, "
                                             f"vol prior for size)"),
                                     does_not_cover=dnc, units="Brier skill score vs the declared control (fraction)",
                                     scope=fam_scope(f, c, hint))
    row_ledger = {
        "ledger_lines": stats.get("n_lines"), "unparseable_family_lines": stats.get("unparseable_family_lines"),
        "rows_in_families": len(rows), "voided": len(voided), "pending_ungraded": len(pending),
        "graded_now": len(graded_all),
        f"graded_but_resolved_after_{a.graded_by}": len(graded_all) - len(sample),
        "sample_resolved_by_graded_by": len(sample),
        "excluded_made_at_or_after_window_start": len(late), "excluded_no_session": len(nowin),
        "scored_clean": len(clean),
        "check": len(voided) + len(pending) + len(graded_all) == len(rows)
                 and len(late) + len(nowin) + len(clean) == len(sample),
    }
    if not row_ledger["check"]:
        raise SystemExit(f"REFUSED: the row ledger does not add up: {row_ledger}")
    after_counts = count_files([Path(x) for x in live_folders])
    inputs = [input_row(pred, newest=stats.get("newest_made_at"), newest_basis="max made_at over every ledger row")]
    audit = panel_audit(bars)
    for bp, au in zip(bars, audit["files"]):
        inputs.append(input_row(bp, newest=au.get("panel_last_session"), newest_basis="max bar date"))
    pk = pooled.get("skill_vs_declared_control") or {}
    receipt = {
        "schema": "ch12_news_grade/forecasts/2", "run_id": a.run_id,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "PRODUCT_EXPERIMENT grade of forward rows; RESEARCH_CLAIM boundary not reached; no claim",
        "question": ("Did the rule-based news_digest insider / positioning / congress forecasts carry skill over "
                     "their declared controls?"),
        "headline": {
            "pooled": {"verdict": verdicts["pooled"]["verdict"], "n": pooled.get("n"),
                       "n_effective_blocks": pk.get("n_blocks_used"), "brier": pooled.get("brier"),
                       "brier_const_0_5": 0.25, "brier_declared_control": pooled.get("brier_declared_control"),
                       "brier_climatology": pooled.get("brier_climatology"), "skill": pk.get("skill"),
                       "se": pk.get("se"), "t": pk.get("t"), "mde_80pct_power": pk.get("mde_80pct_power")},
            "by_family": {f: {"verdict": verdicts[f]["verdict"], "scope_sentence": verdicts[f]["scope_sentence"],
                              "n": res_clean[f]["all"].get("n"),
                              "n_effective_blocks": (res_clean[f]["all"].get("skill_vs_declared_control") or {}).get("n_blocks_used"),
                              "brier": res_clean[f]["all"].get("brier"),
                              "brier_climatology": res_clean[f]["all"].get("brier_climatology"),
                              "brier_declared_control": res_clean[f]["all"].get("brier_declared_control"),
                              "skill": (res_clean[f]["all"].get("skill_vs_declared_control") or {}).get("skill"),
                              "t": (res_clean[f]["all"].get("skill_vs_declared_control") or {}).get("t"),
                              "mde_80pct_power": (res_clean[f]["all"].get("skill_vs_declared_control") or {}).get("mde_80pct_power"),
                              "reliability_resolution": (res_clean[f]["all"].get("reliability_resolution_by_stated_p")),
                              "direction_lines": {k: ((res_clean[f]["all"].get("direction") or {}).get(k) or {}).get("mean")
                                                  for k in ("raw_signed_return_gross", "signed_excess_vs_spy_gross",
                                                            "signed_excess_vs_spy_net_20bps_rt",
                                                            "signed_excess_over_band_peers", "hit_rate")},
                              "top5_share_of_brier_excess": (res_clean[f]["all"].get("tail_brier_minus_control") or {}).get("top5_share_of_total")}
                          for f in FAMILIES},
            "cost": "none charged by the ledger (a forecast is not a trade); the direction net line charges 20 bps round trip",
            "views_tried": 7},
        "sample": {"rule": (f"specialist in {list(FAMILIES)}, outcome not null, void_reason empty, resolved_at <= "
                            f"{a.graded_by}, made strictly before its window's entry close"),
                   "row_ledger": row_ledger,
                   "by_family": dict(Counter(r["specialist"] for r in sample)),
                   "by_family_scored_clean": dict(Counter(r["specialist"] for r in clean)),
                   "by_family_all_graded_now": dict(Counter(r["specialist"] for r in graded_all)),
                   "brier_recomputed_mismatches": mism,
                   "made_at_range": [min(r["made_at"] for r in sample), max(r["made_at"] for r in sample)]},
        "grading_rule": ("backend.services.belief_state.resolve_one: window = horizon+1 closes starting at the first bar "
                         "on or after the made_at DATE; beats_benchmark: outcome = stock return > SPY return; "
                         "abs_move_exceeds: |return| > threshold (one trailing sigma); Brier = (p - outcome)^2"),
        "pit": {"rule": ("a row is excluded when its window's entry close (16:00 ET of the first session on/after the "
                         "made_at date) is not after made_at"),
                "n_excluded_made_after_window_start": len(late),
                "excluded_by_family": dict(Counter(r["specialist"] for r in late)),
                "excluded_made_at_hours_utc": dict(Counter(r["made_at"][11:13] for r in late)),
                "n_no_session_found": len(nowin),
                "gap_h_min": _r(gaps.min(), 2) if gaps.size else None,
                "gap_h_median": _r(float(np.median(gaps)), 2) if gaps.size else None,
                "gap_h_min_kept": _r(min(r["_win"]["gap_h"] for r in clean), 2) if clean else None},
        "peer_check": peer_info,
        "regrade_on_panel": {**dict(regr), "note": ("outcome recomputed with belief_state.resolve_one on the bars panel; "
                                                    "a disagreement is a price-source difference or a window shift")},
        "results_clean": res_clean,
        "results_pooled": pooled,
        "results_including_late_rows": {f: {"all": score_cell([r for r in sample if r["specialist"] == f], rng=rng,
                                                              n_boot=a.n_boot, full=False)} for f in FAMILIES},
        "extension_all_graded_now": {f: {"all": score_cell([r for r in graded_all if r["specialist"] == f
                                                           and (r["_win"]["gap_h"] or -1) > 0],
                                                          rng=rng, n_boot=a.n_boot, full=False)} for f in FAMILIES},
        "verdicts": verdicts,
        "method": {"mde": (f"(t_0.975 + t_0.80) at df = n_blocks - 1, x block-bootstrap SE ({a.n_boot} resamples, "
                           f"seed {a.seed}); the coarser of two block schemes sets SE and df"),
                   "blocks": ("(1) forecast date (made_at[:10]); (2) non-overlapping horizon windows (h, entry session // h): "
                              "5-session windows written on consecutive days overlap, so (2) is the honest count"),
                   "views": ["skill vs declared control (verdict)", "skill vs climatology", "raw probability before shrink",
                             "direction hit rate", "signed excess vs SPY (raw, gross, net)", "signed excess vs band peers",
                             "with/without late rows; sample vs every row graded now"]},
        "inputs": inputs,
        "live_folder_file_counts": {"before": before_counts, "after": after_counts,
                                    "note": "scheduled jobs write these folders; a change is theirs, this run writes only --out"},
        "claims_promoted": "none",
    }
    path = out / f"ch12_news_forecasts_{a.run_id}.json"
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print(f"live folder file counts before {before_counts}")
    print(f"live folder file counts after  {after_counts}")
    print(f"row ledger {row_ledger}")
    for f in FAMILIES + ("pooled",):
        c = pooled if f == "pooled" else res_clean[f]["all"]
        sk = c.get("skill_vs_declared_control") or {}
        print(f"{f}: n={c.get('n')} blocks={sk.get('n_blocks_used')} brier={c.get('brier')} "
              f"clim={c.get('brier_climatology')} ref={c.get('brier_declared_control')} skill={sk.get('skill')} "
              f"se={sk.get('se')} t={sk.get('t')} mde={sk.get('mde_80pct_power')} -> {verdicts[f]['verdict']}")
    print(f"receipt {path}")
    return 0


# ─────────────────────────────── CLI ────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="ch12_news_grade", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    b = sub.add_parser("buys")
    b.add_argument("--fm-dir", required=True)
    b.add_argument("--digest-dir", required=True)
    b.add_argument("--bars", action="append", required=True, help="later file wins a clash")
    b.add_argument("--universe", default=None, help="potential_universe jsonl (identity.sector)")
    b.add_argument("--out", required=True)
    b.add_argument("--role", default="hack6")
    b.add_argument("--before", default="2026-11-01")
    b.add_argument("--k", type=int, default=50)
    b.add_argument("--seed", type=int, default=DEFAULT_SEED)
    b.add_argument("--h", type=int, default=5)
    b.add_argument("--cost-bps-side", type=float, default=10.0)
    b.add_argument("--panel-start", default="2026-05-01")
    b.add_argument("--exclusion-hours", type=float, default=NEWS_EXCLUSION_HOURS)
    b.add_argument("--run-id", default=rid)
    f = sub.add_parser("forecasts")
    f.add_argument("--predictions", required=True)
    f.add_argument("--bars", action="append", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--graded-by", default="2026-11-08")
    f.add_argument("--seed", type=int, default=DEFAULT_SEED)
    f.add_argument("--n-boot", type=int, default=2000)
    f.add_argument("--k", type=int, default=50)
    f.add_argument("--panel-start", default="2026-05-01")
    f.add_argument("--run-id", default=rid)
    a = ap.parse_args(argv)
    if a.k < 20:
        print("REFUSED: --k must be >= 20")
        return 2
    return run_buys(a) if a.cmd == "buys" else run_forecasts(a)


if __name__ == "__main__":
    raise SystemExit(main())
