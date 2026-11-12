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
"effect visible at this sample" / "cannot distinguish" / "negative at this
sample", and every verdict names what it covers and what it does not.
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

#: 80% power at a two-sided 5% test: MDE = (1.96 + 0.84) x SE.
MDE_Z = 2.8
#: |mean| beyond this many SEs is "visible"/"negative"; inside it, cannot distinguish.
VERDICT_Z = 2.0
FAMILIES = ("news_digest:insider_v0", "news_digest:positioning_v0", "news_digest:congress_v0")
DEFAULT_SEED = 20261112

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


def input_row(p: Path) -> dict:
    p = Path(p)
    if p.is_dir():
        files = sorted(x for x in p.rglob("*") if x.is_file())
        h = hashlib.sha256()
        for f in files:
            h.update(f.name.encode())
            h.update(sha256_of(f).encode())
        return {"path": str(p), "kind": "dir", "n_files": len(files),
                "bytes": sum(f.stat().st_size for f in files), "sha256_of_member_hashes": h.hexdigest()}
    return {"path": str(p), "kind": "file", "bytes": p.stat().st_size, "sha256": sha256_of(p)}


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


def scoped_verdict(effect: Optional[float], se: Optional[float], *, covers: str,
                   does_not_cover: str, units: str) -> dict:
    """The three-word verdict, decided by a rule fixed before any number was read."""
    if effect is None or se is None or not math.isfinite(effect) or not math.isfinite(se) or se <= 0:
        label = "CANNOT DETERMINE"
        why = "no standard error (fewer than two blocks or no rows)"
    elif effect > VERDICT_Z * se:
        label, why = "effect visible at this sample", f"mean {effect:+.4g} > {VERDICT_Z:g} x SE {se:.4g}"
    elif effect < -VERDICT_Z * se:
        label, why = "negative at this sample", f"mean {effect:+.4g} < -{VERDICT_Z:g} x SE {se:.4g}"
    else:
        label = "cannot distinguish"
        why = (f"|mean| {abs(effect):.4g} is inside {VERDICT_Z:g} x SE {se:.4g}; the MDE "
               f"{MDE_Z * se:.4g} is larger than the effect")
    return {"verdict": label, "why": why, "effect": _r(effect), "se": _r(se),
            "mde_80pct_power": _r(MDE_Z * se) if se else None, "units": units,
            "covers": covers, "does_not_cover": does_not_cover,
            "rule": (f"visible if mean > {VERDICT_Z:g} SE, negative if mean < -{VERDICT_Z:g} SE, "
                     f"else cannot distinguish; SE from the coarser of the block schemes; "
                     f"MDE = {MDE_Z:g} x SE (80% power, two-sided 5%)")}


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

def load_news_buys(fm_dir: Path, *, role: str, before: Optional[str]) -> list[dict]:
    rows = [json.loads(l) for l in (Path(fm_dir) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    buys = [r for r in rows if r.get("role") == role and r.get("row") == "decision"
            and r.get("kind") == "buy" and r.get("mode") == "LIVE" and not r.get("refused")
            and (before is None or str(r.get("session")) < before)]
    return sorted(buys, key=lambda r: (r["t"], r["symbol"]))


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


def news_tickers_by_session(digest_dir: Path, sessions: Iterable[date], *, hours_before: float = 36.0) -> dict:
    """Every ticker any typed implication named in a world digest stamped in
    [close(d-1) - hours_before, close(d)) -- the names that had a news trigger
    available on session d. Controls are drawn from outside this set."""
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
        lo = hi - timedelta(hours=24 + hours_before)
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


def excess(panel: Panel, sym: str, d0: date, h: int, cost_rt: float,
           entry_px: Optional[float] = None, spy_entry: Optional[float] = None) -> Optional[float]:
    d1 = panel.offset(d0, h)
    p0 = entry_px if entry_px is not None else panel.px(sym, d0)
    p1 = panel.px(sym, d1)
    s0 = spy_entry if spy_entry is not None else panel.px("SPY", d0)
    s1 = panel.px("SPY", d1)
    if None in (p0, p1, s0, s1) or not p0 or not s0:
        return None
    return (p1 / p0 - 1.0) - (s1 / s0 - 1.0) - cost_rt


def grade_buys(buys: list[dict], panel: Panel, *, news_by_session: dict, sector_of: dict, k: int,
               seed: int, h: int, cost_rt: float, no_chase: Optional[float], use_fill: bool) -> tuple[list[dict], dict]:
    units, skipped = [], Counter()
    feats: dict[date, Any] = {}
    bought_on: dict[date, set[str]] = defaultdict(set)
    for b in buys:
        d0 = panel.entry_session(parse_ts(b["t"]))
        b["_entry"] = d0
        if d0:
            bought_on[d0].add(b["symbol"])
    ctrl_dead = 0
    for b in buys:
        d0 = b["_entry"]
        if d0 is None or panel.offset(d0, h) is None:
            skipped["PENDING: no bar 5 sessions after entry"] += 1
            continue
        entry_px = spy_px = None
        if use_fill:
            if not b.get("fill_price"):
                skipped["NO_FILL"] += 1
                continue
            entry_px = b["fill_price"]
            v = panel.vwap.at[d0, "SPY"] if "SPY" in panel.vwap.columns else None
            spy_px = float(v) if v is not None and np.isfinite(v) else None
        ex = excess(panel, b["symbol"], d0, h, cost_rt, entry_px, spy_px)
        if ex is None:
            skipped["NO_BARS_FOR_BUY"] += 1
            continue
        if d0 not in feats:
            feats[d0] = panel.features_before(d0)
        excl = set(news_by_session.get(d0, set())) | bought_on[d0]
        rng = np.random.default_rng([seed, int(hashlib.sha256(b["coid"].encode()).hexdigest()[:12], 16)])
        ctrls, band, pool_n = draw_controls(feats[d0], sym=b["symbol"], sector_of=sector_of, excluded=excl,
                                            k=k, rng=rng, no_chase=no_chase)
        cx = []
        for c in ctrls:
            v = excess(panel, c, d0, h, cost_rt)
            if v is None:
                ctrl_dead += 1
                continue
            cx.append(v)
        if len(cx) < min(20, k):
            skipped[f"FEWER_THAN_20_CONTROLS ({band})"] += 1
            continue
        cx_a = np.array(cx)
        pct = float((np.sum(cx_a < ex) + 0.5 * np.sum(cx_a == ex)) / cx_a.size)
        units.append({"coid": b["coid"], "symbol": b["symbol"], "decided_utc": b["t"], "entry": str(d0),
                      "exit": str(panel.offset(d0, h)), "month": str(d0)[:7],
                      "block5": panel.idx[d0] // h, "entry_kind": b["entry_kind"],
                      "entry_basis": "fill price; SPY at its session VWAP" if use_fill else "close of entry session",
                      "excess_news": ex, "excess_ctrl_mean": float(cx_a.mean()),
                      "excess_ctrl_median": float(np.median(cx_a)), "d": ex - float(cx_a.mean()),
                      "pct_in_controls": pct, "n_controls": int(cx_a.size), "band": band, "band_pool": pool_n,
                      "sector": sector_of.get(b["symbol"]), "fill_status": b.get("fill_status"),
                      "trigger": {kk: b["trigger"].get(kk) for kk in ("kind", "digest", "d", "n")},
                      "themes": [i.get("theme") for i in b["trigger"].get("implications") or []][:3]})
    return units, {"skipped": dict(skipped), "control_draws_without_exit_bar": ctrl_dead}


def summarise_units(units: list[dict], *, h: int) -> dict:
    if not units:
        return {"n": 0}
    d = np.array([u["d"] for u in units])
    exn = np.array([u["excess_news"] for u in units])
    exc = np.array([u["excess_ctrl_mean"] for u in units])
    pct = np.array([u["pct_in_controls"] for u in units])
    se_date = block_se(d, [u["entry"] for u in units])
    se_wk = block_se(d, [u["block5"] for u in units])
    ses = [s["se"] for s in (se_date, se_wk) if s["se"] is not None]
    se_used = max(ses) if ses else None
    by_month = {}
    for m in sorted({u["month"] for u in units}):
        x = [u["d"] for u in units if u["month"] == m]
        by_month[m] = {"n": len(x), "n_dates": len({u["entry"] for u in units if u["month"] == m}),
                       "mean_d": _r(np.mean(x)),
                       "mean_excess_news": _r(np.mean([u["excess_news"] for u in units if u["month"] == m]))}
    lomo = {m: _r(np.mean([u["d"] for u in units if u["month"] != m])) if any(u["month"] != m for u in units)
            else None for m in by_month}
    dates = sorted({u["entry"] for u in units})
    by_date = {dt: {"n": sum(1 for u in units if u["entry"] == dt),
                    "mean_d": _r(np.mean([u["d"] for u in units if u["entry"] == dt]))} for dt in dates}
    lodo = [np.mean([u["d"] for u in units if u["entry"] != dt]) for dt in dates if len(dates) > 1]
    order = sorted(units, key=lambda u: -u["d"])
    tot = float(d.sum())
    top5 = float(sum(u["d"] for u in order[:5]))
    abs_tot = float(np.abs(d).sum())
    hist, _ = np.histogram(pct, bins=10, range=(0.0, 1.0))
    try:
        from scipy import stats as _st
        ks = _st.kstest(pct, "uniform")
        ks_out = {"statistic": _r(ks.statistic), "p_value_rows_iid": _r(ks.pvalue),
                  "note": "rows are not independent (shared dates); read the date-block SE of the mean percentile"}
    except Exception as exc:                                    # noqa: BLE001
        ks_out = {"error": f"{type(exc).__name__}"}
    pct_se = block_se(pct, [u["block5"] for u in units])
    trim = np.sort(d)[max(1, int(0.05 * d.size)):-max(1, int(0.05 * d.size))] if d.size >= 20 else d
    return {
        "n": int(d.size), "n_entry_dates": len(dates), "n_nonoverlapping_5_session_blocks": se_wk["n_blocks"],
        "mean_excess_news": _r(exn.mean()), "median_excess_news": _r(np.median(exn)),
        "mean_excess_controls": _r(exc.mean()), "median_excess_controls": _r(np.median(exc)),
        "mean_d_news_minus_controls": _r(d.mean()), "median_d": _r(np.median(d)),
        "trimmed_mean_d_5pct_each_tail": _r(trim.mean()),
        "share_d_positive": _r(float((d > 0).mean())),
        "se_by_entry_date": se_date, "se_by_5_session_block": se_wk, "se_used": _r(se_used),
        "t_vs_se_used": _r(d.mean() / se_used) if se_used else None,
        "mde_80pct_power": _r(MDE_Z * se_used) if se_used else None,
        "by_month": by_month, "leave_one_month_out_mean_d": lomo, "by_entry_date": by_date,
        "leave_one_date_out_min_mean_d": _r(min(lodo)) if lodo else None,
        "leave_one_date_out_max_mean_d": _r(max(lodo)) if lodo else None,
        "tail": {"top5": [{"symbol": u["symbol"], "entry": u["entry"], "d": _r(u["d"]),
                           "excess_news": _r(u["excess_news"])} for u in order[:5]],
                 "bottom5": [{"symbol": u["symbol"], "entry": u["entry"], "d": _r(u["d"]),
                              "excess_news": _r(u["excess_news"])} for u in order[-5:]],
                 "top5_sum_d": _r(top5), "total_sum_d": _r(tot),
                 "top5_share_of_total": _r(top5 / tot) if abs(tot) > 1e-12 else None,
                 "top5_by_abs_share_of_sum_abs": _r(sum(sorted(np.abs(d))[-5:]) / abs_tot) if abs_tot else None},
        "percentile_in_own_controls": {
            "mean": _r(pct.mean()), "median": _r(np.median(pct)), "se_by_5_session_block": pct_se["se"],
            "deciles_counts": [int(x) for x in hist],
            "note": "uniform on [0,1] (mean 0.5, ~n/10 per decile) means the news trigger carried no information "
                    "beyond its band at this horizon",
            "ks_vs_uniform": ks_out},
    }


def run_buys(a) -> int:
    from backend.services import world_digest as WD  # noqa: F401  -- fails loud if the signal rule moved
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fm = Path(a.fm_dir)
    if not (fm / "decisions.jsonl").exists():
        print(f"CANNOT DETERMINE: {fm / 'decisions.jsonl'} does not exist")
        return 2
    all_live = load_news_buys(fm, role=a.role, before=None)
    buys = load_news_buys(fm, role=a.role, before=a.before)
    if not buys:
        print(f"CANNOT DETERMINE: no LIVE {a.role} buy decisions before {a.before} in {fm / 'decisions.jsonl'}")
        return 2
    meta = attach_fills_and_triggers(buys, fm, Path(a.digest_dir), role=a.role)
    bars = [Path(p) for p in a.bars]
    long_df = load_panel(bars, start=a.panel_start)
    panel = Panel(long_df)
    del long_df
    sessions = sorted({panel.entry_session(parse_ts(b["t"])) for b in buys} - {None})
    news_by = news_tickers_by_session(Path(a.digest_dir), sessions)
    sector_of = load_sector_map(Path(a.universe) if a.universe else None)
    cost_rt = 2.0 * a.cost_bps_side / 1e4
    common = dict(news_by_session=news_by, sector_of=sector_of, k=a.k, seed=a.seed, h=a.h, cost_rt=cost_rt)
    variants = {
        "V1_primary_all_buys_close_entry": dict(no_chase=2.0, use_fill=False, sel=lambda b: True),
        "V2_new_entries_only": dict(no_chase=2.0, use_fill=False, sel=lambda b: b["entry_kind"] == "new_entry"),
        "V3_filled_from_fill_price": dict(no_chase=2.0, use_fill=True, sel=lambda b: True),
        "V4_controls_without_no_chase_filter": dict(no_chase=None, use_fill=False, sel=lambda b: True),
    }
    res, units_primary = {}, []
    for name, v in variants.items():
        sel = [b for b in buys if v["sel"](b)]
        units, info = grade_buys(sel, panel, no_chase=v["no_chase"], use_fill=v["use_fill"], **common)
        res[name] = {"n_selected": len(sel), **info, "summary": summarise_units(units, h=a.h)}
        if name.startswith("V1"):
            units_primary = units
    p = res["V1_primary_all_buys_close_entry"]["summary"]
    covers = (f"{a.role}'s LIVE news-sleeve buy decisions (contract hack6_v2, policy 12fa05317df05ce1) "
              f"before {a.before}: {p.get('n')} buys on {p.get('n_entry_dates')} entry dates, graded at {a.h} "
              f"sessions close-to-close, SPY-adjusted, {a.cost_bps_side:g} bps per side, against {a.k} matched "
              f"non-news names per buy")
    verdict = scoped_verdict(p.get("mean_d_news_minus_controls"), p.get("se_used"), covers=covers,
                             does_not_cover=("news as a mechanism in general; other horizons (20 sessions); "
                                             "short or risk-off use of news; the digest after typing resumed "
                                             "(11-10 onward); a sized or ranked news book; any other account"),
                             units="5-session excess return, fraction (0.01 = 1%)")
    sess_counts = Counter(str(b["session"]) for b in all_live)
    receipt = {
        "schema": "ch12_news_grade/buys/1", "run_id": a.run_id, "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "PRODUCT_EXPERIMENT (a grade of past paper decisions; no claim)",
        "question": "Did the names the hack6 news sleeve bought beat names from the same band that had no news trigger, over the 5 sessions the contract holds them?",
        "sample": {"rule": f"decisions.jsonl rows with role={a.role}, row=decision, kind=buy, mode=LIVE, refused empty, session < {a.before}",
                   "n": len(buys), "first_session": min(str(b['session']) for b in buys),
                   "last_session": max(str(b['session']) for b in buys),
                   "all_live_buys_any_date": len(all_live), "live_buys_by_session": dict(sorted(sess_counts.items())),
                   "entry_kinds": dict(Counter(b["entry_kind"] for b in buys)), **meta},
        "method": {"horizon_sessions": a.h, "entry": "close of the first session whose 16:00 ET close is after the decision timestamp (V3: the recorded fill price, SPY at that session's VWAP)",
                   "exit": f"close {a.h} sessions after the entry session", "benchmark": "SPY over the same closes",
                   "cost": f"{a.cost_bps_side:g} bps per side ({2 * a.cost_bps_side:g} bps round trip), the contract's declared rate, charged to news and controls alike",
                   "controls": {"k": a.k, "seed": a.seed, "rng": "np.random.default_rng([seed, sha256(coid)[:12]])",
                                "band": "first tier with >= k names: sector x 20-session-median-dollar-volume quintile (potential_universe identity.sector); sector x dv tercile; dv quintile x 63-session-vol tercile; dv quintile",
                                "band_revision": "the sector x dv tercile tier was added after the first development run (dev1), which matched only 15 of 83 buys on sector; both runs are reported",
                                "eligibility": "in the panel with >= 40 of 63 sessions of history before entry; not named by any typed ticker implication in any world digest stamped in the 60 h before the entry close; not bought by the account that session; not SPY; V1-V3 also apply the contract's no-chase filter (5-session move <= 2 sigma)",
                                "features_known_at": "bars through the session before entry"},
                   "percentile": "share of the buy's own controls with a lower excess (ties half)",
                   "blocks": "SE of the mean of d with one observation per entry date and, separately, per non-overlapping 5-session block; the coarser (larger) SE is used",
                   "variants_tried": list(variants)},
        "panel": {**panel_audit(bars), "sessions_loaded_from": a.panel_start,
                  "calendar_last_session": str(panel.sessions[-1])},
        "results": res, "verdict": verdict,
        "units_primary": [{k2: (_r(v2) if isinstance(v2, float) else v2) for k2, v2 in u.items()} for u in units_primary],
        "inputs": [input_row(fm / "decisions.jsonl"), input_row(fm / "runs"), input_row(Path(a.digest_dir))]
                  + [input_row(b) for b in bars] + ([input_row(Path(a.universe))] if a.universe else []),
        "claims_promoted": "none",
    }
    path = out / f"ch12_news_buys_{a.run_id}.json"
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print(f"buys: n={len(buys)} graded={p.get('n')} dates={p.get('n_entry_dates')} "
          f"mean d={p.get('mean_d_news_minus_controls')} se={p.get('se_used')} mde={p.get('mde_80pct_power')} "
          f"pct mean={p.get('percentile_in_own_controls', {}).get('mean')} -> {verdict['verdict']}")
    print(f"receipt {path}")
    return 0


# ─────────────────────────────── Part B: the forecasts ──────────────────────

def load_family_forecasts(path: Path, families: Sequence[str] = FAMILIES) -> list[dict]:
    """Stream the ledger (it is large and rewritten in place: read a copy)."""
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if "news_digest:" not in line:
                continue
            r = json.loads(line)
            if r.get("specialist") in families:
                out.append(r)
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
    """Skill = 1 - BS/BS_ref with a date-block bootstrap SE. ref None -> the
    cell's own climatology (its base rate), recomputed inside every resample."""
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
        return {"skill": _r(full), "se": None, "mde_80pct_power": None, "n_blocks": len(keys)}
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), size=len(keys))
        ix = np.concatenate([np.array(by[keys[j]]) for j in pick])
        v = skill(ix)
        if math.isfinite(v):
            vals.append(v)
    se = float(np.std(vals, ddof=1)) if len(vals) > 1 else None
    return {"skill": _r(full), "se": _r(se), "mde_80pct_power": _r(MDE_Z * se) if se else None,
            "n_blocks": len(keys)}


def _two_block_se(values: Sequence[float], rows: Sequence[dict]) -> dict:
    """Block SE of a mean two ways: forecast date, and non-overlapping horizon
    windows (h, entry session // h). Same-horizon windows that overlap share
    their returns, so the date count overstates the information; the coarser
    SE is the one a verdict reads."""
    d = block_se(values, [r["made_at"][:10] for r in rows])
    hz = block_se(values, [r.get("_hblock") for r in rows])
    ses = [x["se"] for x in (d, hz) if x["se"] is not None]
    se = max(ses) if ses else None
    return {"mean": _r(float(np.mean(values))) if len(values) else None, "se_date_blocks": d["se"],
            "n_date_blocks": d["n_blocks"], "se_horizon_blocks": hz["se"], "n_horizon_blocks": hz["n_blocks"],
            "se_used": _r(se), "mde_80pct_power": _r(MDE_Z * se) if se else None}


def score_cell(rows: list[dict], *, rng: np.random.Generator, n_boot: int) -> dict:
    from backend.services import calibration as CAL
    if not rows:
        return {"n": 0}
    p = np.array([float(r["probability"]) for r in rows])
    y = np.array([float(r["outcome"]) for r in rows])
    dblocks = [r["made_at"][:10] for r in rows]
    hblocks = [r.get("_hblock") for r in rows]
    bs = float(np.mean((p - y) ** 2))
    base = float(y.mean())
    obs = {r["observable"] for r in rows}
    # the row's DECLARED control: a 0.5 coin for direction, the vol prior for size
    ref_decl = np.array([float((r.get("inputs_used") or {}).get("vol_prior_p"))
                         if r["observable"] == "abs_move_exceeds" and (r.get("inputs_used") or {}).get("vol_prior_p") is not None
                         else 0.5 for r in rows])
    raw = np.array([float(r.get("raw_probability") if r.get("raw_probability") is not None else r["probability"])
                    for r in rows])

    def skill(pp: np.ndarray, ref: Optional[np.ndarray]) -> dict:
        a_ = _skill_boot(pp, y, ref, dblocks, rng, n_boot)
        b_ = _skill_boot(pp, y, ref, hblocks, rng, n_boot)
        ses = [x for x in (a_["se"], b_["se"]) if x is not None]
        se = max(ses) if ses else None
        return {"skill": a_["skill"], "se_date_blocks": a_["se"], "n_date_blocks": a_["n_blocks"],
                "se_horizon_blocks": b_["se"], "n_horizon_blocks": b_["n_blocks"],
                "se": _r(se), "mde_80pct_power": _r(MDE_Z * se) if se else None}

    dec = CAL.brier_decomposition(p, y)
    out: dict[str, Any] = {
        "n": int(p.size), "n_date_blocks": len(set(dblocks)), "n_horizon_blocks": len(set(hblocks)),
        "observables": sorted(obs),
        "brier": _r(bs), "base_rate": _r(base), "brier_climatology": _r(base * (1 - base)),
        "brier_const_0_5": 0.25, "brier_declared_control": _r(float(np.mean((ref_decl - y) ** 2))),
        "brier_raw_probability_before_shrink": _r(float(np.mean((raw - y) ** 2))),
        "p_distinct": sorted({_r(x, 4) for x in p})[:12], "p_min": _r(p.min()), "p_max": _r(p.max()),
        "skill_vs_climatology": skill(p, None),
        "skill_vs_declared_control": skill(p, ref_decl),
        "skill_raw_probability_vs_declared_control": skill(raw, ref_decl),
        "decomposition": {k: (_r(v) if isinstance(v, float) else v) for k, v in dec.items() if k != "bins"},
        # by DISTINCT stated probability: with four or fewer distinct values the
        # Murphy bins merge, so this is the reliability table the reader can use
        "reliability_by_stated_p": [
            {"p": _r(v, 4), "n": int((p == v).sum()), "mean_outcome": _r(float(y[p == v].mean()), 4),
             "outcome_se": _r(math.sqrt(max(y[p == v].mean() * (1 - y[p == v].mean()), 0) / max((p == v).sum(), 1)), 4)}
            for v in sorted(set(p.tolist()))],
    }
    dirn = [r for r in rows if r["observable"] == "beats_benchmark" and float(r["probability"]) != 0.5]
    if dirn:
        hit = [float((float(r["probability"]) > 0.5) == bool(r["outcome"])) for r in dirn]
        sg = [r for r in dirn if r.get("vs_benchmark") is not None]
        signed = [(1.0 if float(r["probability"]) > 0.5 else -1.0) * float(r["vs_benchmark"]) for r in sg]
        out["direction"] = {
            "n": len(dirn), "hit_rate": _two_block_se(hit, dirn),
            "signed_excess_vs_spy_gross": _two_block_se(signed, sg) if sg else None,
            "note": "signed by the forecast's side (p > 0.5 long, p < 0.5 short); gross of costs; a forecast is not a trade"}
        pe = [r for r in dirn if r.get("_peer") is not None]
        if pe:
            out["direction"]["signed_excess_over_band_peers"] = {
                "n": len(pe), **_two_block_se([r["_peer"] for r in pe], pe),
                "mean_pct_in_peers": _r(float(np.mean([r["_peer_pct"] for r in pe]))),
                "note": ("the row's own return minus the mean of K band-matched names (same entry and exit closes, "
                         "not named by any of these families that day), signed by the forecast's side: "
                         "separates the rule from the band's beta vs SPY")}
    return out


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
        ctrls, band, _n = draw_controls(feats[d0], sym=r["ticker"], sector_of={}, excluded=named[r["made_at"][:10]],
                                        k=k, rng=rng, no_chase=None)
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
    return {"k": k, "band": "dv quintile x 63-session-vol tercile (no sector tier: mostly small caps)",
            **dict(why)}


def run_forecasts(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pred = Path(a.predictions)
    if not pred.exists():
        print(f"CANNOT DETERMINE: {pred} does not exist")
        return 2
    rows = load_family_forecasts(pred)
    graded_all = [r for r in rows if r.get("outcome") is not None and not r.get("void_reason")]
    sample = [r for r in graded_all if a.graded_by is None or str(r.get("resolved_at"))[:10] <= a.graded_by]
    if not sample:
        print(f"CANNOT DETERMINE: no graded {FAMILIES} rows resolved by {a.graded_by} in {pred}")
        return 2
    # recompute the Brier from the rows and check it against the stored one
    mism = sum(1 for r in sample if abs((float(r["probability"]) - float(r["outcome"])) ** 2 - float(r["brier"])) > 1e-9)
    import pandas as pd
    bars = [Path(p) for p in a.bars]
    cal = pd.read_parquet(bars[-1], columns=["symbol", "date"], filters=[("symbol", "==", "SPY")])
    sessions = sorted(pd.to_datetime(cal["date"]).dt.date.unique())
    for r in sample:
        r["_win"] = forecast_window(r, sessions)
    late = [r for r in sample if r["_win"]["gap_h"] is not None and r["_win"]["gap_h"] <= 0]
    nowin = [r for r in sample if r["_win"]["gap_h"] is None]
    clean = [r for r in sample if r["_win"]["gap_h"] is not None and r["_win"]["gap_h"] > 0]
    gaps = np.array([r["_win"]["gap_h"] for r in sample if r["_win"]["gap_h"] is not None])
    sidx = {d: i for i, d in enumerate(sessions)}
    for r in graded_all:
        w = r.get("_win") or forecast_window(r, sessions)
        r["_win"] = w
        e = date.fromisoformat(w["entry"]) if w.get("entry") else None
        r["_hblock"] = (int(r["horizon_days"]), sidx[e] // int(r["horizon_days"])) if e in sidx else None
    peer_info = peer_check(clean, bars, k=a.k, seed=a.seed, panel_start=a.panel_start)
    # re-grade from the bars with the ledger's own resolver, where the panel has the name
    from backend.services import belief_state as BS
    from backend.services import one_event as OE
    closes = OE.load_closes(bars, {r["ticker"] for r in clean})
    regr = Counter()
    for r in clean:
        if r["ticker"] not in closes.columns:
            regr["ticker_not_in_panel"] += 1
            continue
        rec = {k: v for k, v in r.items() if not k.startswith("_")}
        rec.update(outcome=None, brier=None, resolved_at=None)
        px = closes.copy()
        px.index = pd.to_datetime(px.index)
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
            fam[f]["by_month"] = {m: {k: v for k, v in score_cell([r for r in x if r["made_at"][:7] == m], rng=rng,
                                                                  n_boot=200).items()
                                      if k in ("n", "n_date_blocks", "brier", "base_rate", "brier_climatology",
                                               "brier_declared_control", "skill_vs_declared_control", "direction")}
                                  for m in sorted({r["made_at"][:7] for r in x})}
            fam[f]["by_rule"] = {ru: {k: v for k, v in score_cell([r for r in x if (r.get("inputs_used") or {}).get("rule") == ru],
                                                                  rng=rng, n_boot=200).items()
                                      if k in ("n", "n_date_blocks", "brier", "base_rate", "brier_declared_control",
                                               "skill_vs_declared_control", "direction")}
                                 for ru in sorted({(r.get("inputs_used") or {}).get("rule") for r in x} - {None})}
        return fam
    res_clean = cells(clean)
    verdicts = {}
    for f in FAMILIES:
        c = res_clean[f]["all"]
        sk = c.get("skill_vs_declared_control") or {}
        verdicts[f] = scoped_verdict(sk.get("skill"), sk.get("se"),
                                     covers=(f"{f}: {c.get('n')} graded rows made before their window, "
                                             f"{c.get('n_date_blocks')} forecast dates / {c.get('n_horizon_blocks')} non-overlapping horizon windows, "
                                             f"{', '.join(c.get('observables', []))}; "
                                             f"skill = 1 - Brier / Brier(declared control: 0.5 coin for direction, "
                                             f"vol prior for size)"),
                                     does_not_cover=("the underlying insider / short-interest / COT / congress data as a "
                                                     "signal (the stated probabilities are shrunk x0.2 toward 0.5, so "
                                                     "the Brier cannot move far from 0.25 by construction); other horizons; "
                                                     "a traded book on these rules; rows after the sample date"),
                                     units="Brier skill score (fraction)")
    receipt = {
        "schema": "ch12_news_grade/forecasts/1", "run_id": a.run_id,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "RESEARCH_CLAIM boundary not reached: a scoped grade of forward rows; no claim",
        "question": "Did the rule-based news_digest insider / positioning / congress forecasts carry skill over their declared controls?",
        "sample": {"rule": f"specialist in {list(FAMILIES)}, outcome not null, void_reason empty, resolved_at <= {a.graded_by}",
                   "n_rows_in_families": len(rows), "n_graded_all": len(graded_all), "n_sample": len(sample),
                   "by_family": dict(Counter(r["specialist"] for r in sample)),
                   "by_family_all_graded_now": dict(Counter(r["specialist"] for r in graded_all)),
                   "brier_recomputed_mismatches": mism,
                   "made_at_range": [min(r["made_at"] for r in sample), max(r["made_at"] for r in sample)]},
        "grading_rule": ("backend.services.belief_state.resolve_one: window = horizon+1 closes starting at the first bar "
                         "on or after the made_at DATE; beats_benchmark: outcome = stock return > SPY return; "
                         "abs_move_exceeds: |return| > threshold (one trailing sigma); Brier = (p - outcome)^2"),
        "pit": {"rule": "a row is excluded when its window's entry close (16:00 ET of the first session on/after the made_at date) is not after made_at",
                "n_excluded_made_after_window_start": len(late),
                "excluded_by_family": dict(Counter(r["specialist"] for r in late)),
                "excluded_made_at_hours_utc": dict(Counter(r["made_at"][11:13] for r in late)),
                "n_no_session_found": len(nowin),
                "gap_h_min": _r(gaps.min(), 2) if gaps.size else None,
                "gap_h_median": _r(float(np.median(gaps)), 2) if gaps.size else None,
                "gap_h_min_kept": _r(min(r["_win"]["gap_h"] for r in clean), 2) if clean else None},
        "peer_check": peer_info,
        "regrade_on_panel": {**dict(regr), "note": "outcome recomputed with belief_state.resolve_one on the bars panel; a disagreement is a price-source difference or a window shift, read the count"},
        "results_clean": res_clean,
        "results_including_late_rows": {f: {"all": score_cell([r for r in sample if r["specialist"] == f], rng=rng, n_boot=a.n_boot)} for f in FAMILIES},
        "extension_all_graded_now": {f: {"all": score_cell([r for r in graded_all if r["specialist"] == f
                                                           and (r["_win"]["gap_h"] or -1) > 0],
                                                          rng=rng, n_boot=a.n_boot)} for f in FAMILIES},
        "verdicts": verdicts,
        "method": {"mde": f"{MDE_Z:g} x block-bootstrap SE ({a.n_boot} resamples, seed {a.seed}); the coarser of two block schemes",
                   "blocks": ("(1) forecast date (made_at[:10]); (2) non-overlapping horizon windows (h, entry session // h): "
                              "5-session windows written on consecutive days overlap, so (2) is the honest count"),
                   "views": ["skill vs climatology", "skill vs declared control", "raw probability before shrink",
                             "direction hit rate", "signed excess vs SPY", "with/without late rows",
                             "837-row sample vs every row graded now"]},
        "inputs": [input_row(pred)] + [input_row(b) for b in bars],
        "claims_promoted": "none",
    }
    path = out / f"ch12_news_forecasts_{a.run_id}.json"
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    for f in FAMILIES:
        c = res_clean[f]["all"]
        print(f"{f}: n={c.get('n')} dates={c.get('n_date_blocks')} brier={c.get('brier')} "
              f"ref={c.get('brier_declared_control')} skill={c.get('skill_vs_declared_control')} -> {verdicts[f]['verdict']}")
    print(f"sample {len(sample)} (late rows excluded {len(late)}); receipt {path}")
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
    if a.k < 20 if a.cmd == "buys" else False:
        print("REFUSED: --k must be >= 20")
        return 2
    return run_buys(a) if a.cmd == "buys" else run_forecasts(a)


if __name__ == "__main__":
    raise SystemExit(main())
