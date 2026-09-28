"""Contest-book odds: the distribution of a book's RELATIVE return over a contest window.

    python -m scripts.contest_book_odds --book "five=AAA:0.2,BBB:0.2,CCC:0.2,DDD:0.2,EEE:0.2"
    python -m scripts.contest_book_odds --book "..." --book "..." --targets 0.053,0.40,1.50 \\
        --with-earnings --events-per-slot 1,2 --random-control 1000

For each book and each lookback (63 and 252 sessions by default) it prints the
probability that the book's buy-and-hold return over HORIZON sessions beats the
benchmark proxy by each target, with the median, the 5th and the 95th percentile,
under three estimators:

  normal       zero-mean normal, sigma from the realised daily covariance of the
               names and the benchmark (the adversarial reviewer's method);
  windows      every actual overlapping HORIZON-session window inside the lookback
               (fat tails and co-movement as they happened; few independent windows);
  block        a block bootstrap of joint daily return rows (block BLOCK_LEN), which
               keeps same-day co-movement and fat tails with more resolution;
and, with --with-earnings, `block+events`: the same block bootstrap with each
name's own historical earnings-reaction days (EDGAR 8-K item 2.02) removed from
the pool and E resampled reactions added per slot (E from --events-per-slot; E=2
approximates rotating a slot into a second name's print).

Every estimator is DE-MEANED by default (each name's daily log returns are shifted
so that its expected SIMPLE return is zero): a name picked because it was volatile is often a name
that ran, and its past drift is not a forecast. `--keep-drift` prints the raw
version beside it.

Refuses, by name and with exit code 2: a ticker with no bars (or too few in a
lookback), a weight above the contest cap (20%), a negative weight, weights
summing above 1. Cash (1 - sum of weights) earns zero.

The benchmark is a PROXY: the contest scores against the Bloomberg WLS index,
which is not on disk. URTH is used where it covers the lookback, else SPY; the
receipt records which. $0: no LLM, no network, no order.

PRODUCT_EXPERIMENT; nothing here is a claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# ── constants (kept here on purpose: this builder may not touch backend/config.py) ──
POSITION_CAP = 0.20            # contest rule: no single position > 20% of notional
HORIZON = 23                   # Oct 12 - Nov 13 2026 = 24 NYSE sessions; 23 daily returns
LOOKBACKS = (63, 252)
DEFAULT_TARGETS = (0.053, 0.20, 0.40, 1.00)
BLOCK_LEN = 5
N_BLOCK_DRAWS = 20_000
MIN_OBS_FRAC = 0.8             # a name needs >= 80% of the lookback's sessions
BENCH_CANDIDATES = ("URTH", "SPY")
SEED = 20261012
EPS = 1e-9
LICENCE = "PRODUCT_EXPERIMENT; nothing here is a claim."


class BookRefused(ValueError):
    """A book the contest (or this tool) cannot price. The message names every reason."""


# ───────────────────────────── validation ─────────────────────────────

def parse_book(spec: str) -> tuple[str, dict[str, float]]:
    """'name=AAA:0.2,BBB:0.2' -> ('name', {'AAA': 0.2, 'BBB': 0.2})."""
    if "=" in spec:
        name, body = spec.split("=", 1)
    else:
        name, body = "book", spec
    w: dict[str, float] = {}
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        t, v = part.split(":")
        t = t.strip().upper()
        w[t] = w.get(t, 0.0) + float(v)
    return name.strip(), w


def validate_book(weights: dict[str, float], available: Iterable[str], *,
                  cap: float = POSITION_CAP) -> None:
    """Raise BookRefused naming every violation; return None when the book is priceable."""
    avail = {str(s).upper() for s in available}
    why: list[str] = []
    if not weights:
        why.append("empty book")
    for t, v in weights.items():
        if not np.isfinite(v):
            why.append(f"{t}: weight {v} is not finite")
        elif v < 0:
            why.append(f"{t}: negative weight {v} (the contest is long only)")
        elif v > cap + EPS:
            why.append(f"{t}: weight {v:.4f} above the {cap:.0%} position cap")
        if t.upper() not in avail:
            why.append(f"{t}: no bars on disk")
    tot = float(sum(v for v in weights.values() if np.isfinite(v)))
    if tot > 1 + EPS:
        why.append(f"weights sum to {tot:.4f} > 1 (no leverage)")
    if why:
        raise BookRefused("; ".join(why))


# ───────────────────────────── returns ─────────────────────────────

def wide_log_returns(bars: pd.DataFrame, symbols: Iterable[str], asof=None) -> pd.DataFrame:
    """Daily log returns (sessions x symbols) from long bars (symbol, date, close)."""
    syms = {str(s).upper() for s in symbols}
    b = bars[bars["symbol"].astype(str).str.upper().isin(syms)]
    if asof is not None:
        b = b[pd.to_datetime(b["date"]) <= pd.Timestamp(asof)]
    w = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    w.columns = [str(c).upper() for c in w.columns]
    return np.log(w.where(w > 0)).diff().iloc[1:]


def lookback_slice(lr: pd.DataFrame, lookback: int, names: list[str]) -> pd.DataFrame:
    """The last `lookback` sessions for `names`; refuse by name when coverage is short."""
    sub = lr[names].iloc[-lookback:]
    if len(sub) < lookback:
        raise BookRefused(f"only {len(sub)} sessions on disk for a {lookback}-session lookback")
    need = int(math.ceil(MIN_OBS_FRAC * lookback))
    short = [f"{c}: {int(sub[c].notna().sum())}/{lookback} sessions" for c in names
             if sub[c].notna().sum() < need]
    if short:
        raise BookRefused("too few bars in the lookback -- " + "; ".join(short))
    return sub.fillna(0.0)     # a halted session is a zero return


def book_sigma_daily(weights: dict[str, float], lr: pd.DataFrame) -> float:
    """Absolute daily sigma of a fixed-weight book (simple returns); cash has zero variance."""
    names = list(weights)
    r = np.expm1(lr[names].to_numpy(dtype=float))
    w = np.array([weights[n] for n in names])
    if len(names) == 1:
        return float(abs(w[0]) * np.std(r[:, 0], ddof=1))
    cov = np.cov(r, rowvar=False, ddof=1)
    return float(math.sqrt(max(w @ cov @ w, 0.0)))


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _summ(rel: np.ndarray, targets: Iterable[float]) -> dict:
    rel = np.asarray(rel, dtype=float)
    return {"n": int(rel.size),
            "p_beat": {f"{t:+.3f}": float(np.mean(rel > t)) for t in targets},
            "mean": float(rel.mean()), "median": float(np.median(rel)),
            "p05": float(np.quantile(rel, 0.05)), "p95": float(np.quantile(rel, 0.95)),
            "p99": float(np.quantile(rel, 0.99)), "sd": float(rel.std(ddof=1)) if rel.size > 1 else 0.0}


def normal_odds(weights: dict[str, float], bench: Optional[str], lr: pd.DataFrame,
                horizon: int, targets: Iterable[float]) -> dict:
    """Zero-mean normal on the RELATIVE return: sigma_d = sqrt(v' Sigma v), v = (w, -1)."""
    names = list(weights)
    cols = names + ([bench] if bench else [])
    r = np.expm1(lr[cols].to_numpy(dtype=float))
    v = np.array([weights[n] for n in names] + ([-1.0] if bench else []))
    cov = np.atleast_2d(np.cov(r, rowvar=False, ddof=1))
    sd_d = float(math.sqrt(max(v @ cov @ v, 0.0)))
    sd_h = sd_d * math.sqrt(horizon)
    targets = list(targets)
    return {"n": None, "sd_daily_rel": sd_d, "sd": sd_h,
            "p_beat": {f"{t:+.3f}": (_norm_sf(t / sd_h) if sd_h > 0 else float(t < 0)) for t in targets},
            "mean": 0.0, "median": 0.0, "p05": -1.6448536 * sd_h, "p95": 1.6448536 * sd_h,
            "p99": 2.3263479 * sd_h}


def _zero_edge(X: np.ndarray) -> np.ndarray:
    """Shift each column's daily log returns to mean -var/2, so every name's expected SIMPLE
    return is zero (a zero log drift would hand a 5%/day name +2.9% over 23 sessions)."""
    return X - X.mean(axis=0, keepdims=True) - 0.5 * X.var(axis=0, ddof=1, keepdims=True)


def _rel_from_logsums(S: np.ndarray, w: np.ndarray, has_bench: bool) -> np.ndarray:
    """S: draws x (names [+ bench]) summed log returns -> relative simple return per draw."""
    k = len(w)
    book = np.expm1(S[:, :k]) @ w
    return book - (np.expm1(S[:, k]) if has_bench else 0.0)


def window_bootstrap(weights: dict[str, float], bench: Optional[str], lr: pd.DataFrame,
                     horizon: int, targets: Iterable[float], *, demean: bool = True) -> dict:
    """Every overlapping `horizon`-session window inside `lr` (buy-and-hold at the weights)."""
    names = list(weights)
    cols = names + ([bench] if bench else [])
    X = lr[cols].to_numpy(dtype=float)
    if demean:
        X = _zero_edge(X)
    if len(X) < horizon:
        raise BookRefused(f"lookback {len(X)} shorter than the horizon {horizon}")
    c = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(X, axis=0)])
    S = c[horizon:] - c[:-horizon]
    w = np.array([weights[n] for n in names])
    out = _summ(_rel_from_logsums(S, w, bool(bench)), targets)
    out["independent_windows"] = int(len(X) // horizon)
    return out


def block_bootstrap(weights: dict[str, float], bench: Optional[str], lr: pd.DataFrame,
                    horizon: int, targets: Iterable[float], *, demean: bool = True,
                    n_draws: int = N_BLOCK_DRAWS, block: int = BLOCK_LEN, seed: int = SEED,
                    event_jumps: Optional[dict[str, np.ndarray]] = None,
                    event_masks: Optional[dict[str, np.ndarray]] = None,
                    events_per_slot: int = 1) -> dict:
    """Moving-block bootstrap of joint daily rows. With `event_jumps`, each listed name's
    earnings-reaction sessions (`event_masks`, boolean over lr's rows) are zeroed in the pool
    and `events_per_slot` resampled reactions are added per draw."""
    names = list(weights)
    cols = names + ([bench] if bench else [])
    X = lr[cols].to_numpy(dtype=float).copy()
    if event_masks:
        for j, n in enumerate(names):
            m = event_masks.get(n)
            if m is not None and event_jumps and len(event_jumps.get(n, [])):
                X[np.asarray(m, dtype=bool), j] = 0.0
    if demean:
        X = _zero_edge(X)
    T = len(X)
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(horizon / block))
    starts = rng.integers(0, T - block + 1, size=(n_draws, nb))
    S = np.zeros((n_draws, X.shape[1]))
    c = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(X, axis=0)])
    for b in range(nb):
        L = block if b < nb - 1 else horizon - block * (nb - 1)
        s = starts[:, b]
        S += c[s + L] - c[s]
    applied = {}
    if event_jumps:
        for j, n in enumerate(names):
            jm = np.asarray(event_jumps.get(n, []), dtype=float)
            if jm.size == 0:
                continue
            if demean:      # zero-edge: sign-symmetrise (keeps magnitude even with 1 print),
                jm = np.concatenate([jm, -jm])        # then the -var/2 log-drift shift
                jm = jm - 0.5 * jm.var()
            S[:, j] += rng.choice(jm, size=(n_draws, events_per_slot), replace=True).sum(axis=1)
            applied[n] = int(jm.size)
    w = np.array([weights[n] for n in names])
    out = _summ(_rel_from_logsums(S, w, bool(bench)), targets)
    out["block_len"] = block
    if event_jumps is not None:
        out["events_per_slot"] = events_per_slot
        out["names_with_event_history"] = applied
    return out


# ───────────────────────────── earnings reactions ─────────────────────────────

def earnings_reactions(eightk: pd.DataFrame, lr: pd.DataFrame, names: Iterable[str]
                       ) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Per name: 2-session log reactions around each 8-K item 2.02 filing inside lr's dates
    (last session before the filing date -> first session after it, which covers a pre-open
    and an after-close release), and the boolean mask of those sessions over lr's rows."""
    idx = pd.DatetimeIndex(pd.to_datetime(lr.index))
    ek = eightk[["ticker", "filing_date", "items_joined"]].copy()
    ek["t"] = ek["ticker"].astype(str).str.upper()
    ek["d"] = pd.to_datetime(ek["filing_date"], errors="coerce")
    ek = ek[ek["items_joined"].fillna("").astype(str).str.contains("2.02", regex=False)
            & ek["d"].notna()]
    jumps, masks = {}, {}
    for n in names:
        if n not in lr.columns:
            continue
        ds = sorted(set(ek.loc[ek["t"] == n, "d"]))
        m = np.zeros(len(idx), dtype=bool)
        vals = []
        for d in ds:
            i0 = idx.searchsorted(d, side="left")          # first session >= filing date
            i1 = idx.searchsorted(d, side="right")         # first session > filing date
            if i0 == 0 or i1 >= len(idx):
                continue
            rows = list(range(i0, i1 + 1))                 # the filing session (if any) + the next
            v = float(np.nansum(lr[n].to_numpy()[rows]))
            if np.isfinite(v):
                vals.append(v)
                m[rows] = True
        if vals:
            jumps[n] = np.array(vals)
            masks[n] = m
    return jumps, masks


# ───────────────────────────── driver ─────────────────────────────

def pick_bench(lr_all: pd.DataFrame, lookback: int, candidates=BENCH_CANDIDATES) -> Optional[str]:
    for b in candidates:
        if b in lr_all.columns and lr_all[b].iloc[-lookback:].notna().sum() >= lookback - 1:
            return b
    return None


def book_odds(weights: dict[str, float], lr_all: pd.DataFrame, *, lookbacks=LOOKBACKS,
              horizon: int = HORIZON, targets=DEFAULT_TARGETS, keep_drift: bool = False,
              eightk: Optional[pd.DataFrame] = None, events_per_slot=(1,),
              bench_candidates=BENCH_CANDIDATES, n_draws: int = N_BLOCK_DRAWS) -> dict:
    validate_book(weights, lr_all.columns)
    names = list(weights)
    out = {"weights": weights, "cash": float(1 - sum(weights.values())), "by_lookback": {}}
    for L in lookbacks:
        bench = pick_bench(lr_all, L, bench_candidates)
        cols = names + ([bench] if bench else [])
        lr = lookback_slice(lr_all, L, cols)
        row = {"benchmark_proxy": bench, "sessions": [str(pd.Timestamp(lr.index[0]).date()),
                                                      str(pd.Timestamp(lr.index[-1]).date())],
               "sigma_daily_abs": book_sigma_daily(weights, lr),
               "name_sigma_daily": {n: float(np.expm1(lr[n]).std(ddof=1)) for n in names},
               "normal": normal_odds(weights, bench, lr, horizon, targets),
               "windows": window_bootstrap(weights, bench, lr, horizon, targets),
               "block": block_bootstrap(weights, bench, lr, horizon, targets, n_draws=n_draws)}
        if keep_drift:
            row["windows_raw_drift"] = window_bootstrap(weights, bench, lr, horizon, targets, demean=False)
            row["block_raw_drift"] = block_bootstrap(weights, bench, lr, horizon, targets,
                                                     demean=False, n_draws=n_draws)
        if eightk is not None:
            jumps, masks = earnings_reactions(eightk, lr, names)
            for E in events_per_slot:
                row[f"block+events{E}"] = block_bootstrap(
                    weights, bench, lr, horizon, targets, event_jumps=jumps, event_masks=masks,
                    events_per_slot=int(E), n_draws=n_draws)
            row["earnings_reactions"] = {n: {"n": int(len(v)), "median_abs": float(np.median(np.abs(v)))}
                                         for n, v in jumps.items()}
        out["by_lookback"][str(L)] = row
    return out


def random_control(pool: list[str], lr_all: pd.DataFrame, *, k: int = 5, weight: float = 0.20,
                   n: int = 1000, lookback: int = 252, horizon: int = HORIZON,
                   targets=DEFAULT_TARGETS, seed: int = SEED) -> dict:
    """n random k x weight books from `pool`: the spread of P(beat target) under the normal
    estimate, i.e. how much the SHAPE decides versus the names."""
    rng = np.random.default_rng(seed)
    bench = pick_bench(lr_all, lookback)
    need = int(math.ceil(MIN_OBS_FRAC * lookback))
    sub = lr_all.iloc[-lookback:]
    pool = [p for p in pool if p in sub.columns and sub[p].notna().sum() >= need]
    X = np.expm1(sub[pool + ([bench] if bench else [])].fillna(0.0).to_numpy(dtype=float))
    cov = np.cov(X, rowvar=False, ddof=1)
    books, sds = [], []
    for _ in range(n):
        ix = rng.choice(len(pool), size=k, replace=False)
        v = np.zeros(len(pool) + (1 if bench else 0))
        v[ix] = weight
        if bench:
            v[-1] = -1.0
        sds.append(math.sqrt(max(v @ cov @ v, 0.0)) * math.sqrt(horizon))
        books.append(sorted(pool[i] for i in ix))
    sds = np.array(sds)
    p = {f"{t:+.3f}": {"median": float(np.median([_norm_sf(t / s) for s in sds])),
                        "p90": float(np.quantile([_norm_sf(t / s) for s in sds], 0.9))}
         for t in targets}
    return {"n": n, "k": k, "weight": weight, "pool_size": len(pool), "lookback": lookback,
            "benchmark_proxy": bench, "sd_rel_median": float(np.median(sds)),
            "sd_rel_p10_p90": [float(np.quantile(sds, 0.1)), float(np.quantile(sds, 0.9))],
            "p_beat_normal": p, "seed": seed, "books_first_20": books[:20],
            "books_sha256": hashlib.sha256(json.dumps(books).encode()).hexdigest()[:16]}


def load_bars(opt: Path, symbols: Iterable[str]) -> pd.DataFrame:
    syms = {str(s).upper() for s in symbols} | set(BENCH_CANDIDATES)
    parts = []
    p1 = opt / "prices_2025_26" / "bars.parquet"
    if p1.exists():
        b = pd.read_parquet(p1, columns=["symbol", "date", "close"])
        parts.append(b[b["symbol"].isin(syms)])
    p2 = opt / "llm_portfolio" / "global_bars.parquet"
    if p2.exists():
        g = pd.read_parquet(p2, columns=["symbol", "date", "close"])
        g = g[g["symbol"].isin(syms)]
        have = set(parts[0]["symbol"]) if parts else set()
        parts.append(g[~g["symbol"].isin(have)])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["symbol", "date", "close"])


def _fmt(o: dict, targets) -> str:
    ps = "  ".join(f"P>{float(t):+.1%}={o['p_beat'][f'{float(t):+.3f}']:.3f}" for t in targets)
    return f"{ps}  med={o['median']:+.1%}  p05={o['p05']:+.1%}  p95={o['p95']:+.1%}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", action="append", required=True, help="name=T1:w,T2:w (repeatable)")
    ap.add_argument("--targets", default=",".join(str(t) for t in DEFAULT_TARGETS))
    ap.add_argument("--asof", default=None, help="last bar date to use (default: newest on disk)")
    ap.add_argument("--horizon", type=int, default=HORIZON)
    ap.add_argument("--with-earnings", action="store_true")
    ap.add_argument("--events-per-slot", default="1")
    ap.add_argument("--keep-drift", action="store_true")
    ap.add_argument("--random-control", type=int, default=0, help="n random 5x20%% books")
    ap.add_argument("--control-pool", default=None, help="file with one ticker per line")
    ap.add_argument("--draws", type=int, default=N_BLOCK_DRAWS)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)

    from backend import config as _cfg
    opt = Path(_cfg.OPTIMUS_LEDGER_DIR)
    out_dir = Path(a.out_dir) if a.out_dir else opt / "contest"
    targets = [float(x) for x in a.targets.split(",") if x.strip()]
    books = [parse_book(s) for s in a.book]
    pool: list[str] = []
    if a.random_control and a.control_pool:
        pool = [ln.strip().upper() for ln in Path(a.control_pool).read_text().splitlines() if ln.strip()]
    syms = set().union(*[set(w) for _, w in books]) | set(pool)
    bars = load_bars(opt, syms)
    lr_all = wide_log_returns(bars, syms | set(BENCH_CANDIDATES), a.asof)
    eightk = None
    if a.with_earnings:
        eightk = pd.read_parquet(opt / "edgar_8k" / "eightk_items.parquet",
                                 columns=["ticker", "filing_date", "items_joined"])
    eps = [int(x) for x in a.events_per_slot.split(",")]

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + (f"_{a.tag}" if a.tag else "")
    receipt = {"run_id": run_id, "written_utc": now.isoformat(), "licence": LICENCE,
               "script": "scripts/contest_book_odds.py", "argv": argv if argv is not None else sys.argv[1:],
               "horizon_sessions": a.horizon, "targets": targets, "position_cap": POSITION_CAP,
               "bars_last_date": str(pd.Timestamp(lr_all.index[-1]).date()) if len(lr_all) else None,
               "bars_sources": ["prices_2025_26/bars.parquet", "llm_portfolio/global_bars.parquet"],
               "benchmark_note": "WLS is not on disk; URTH where it covers the lookback, else SPY",
               "demeaned": True, "llm_spend_usd": 0.0, "books": {}, "refused": {}}
    rc = 0
    for name, w in books:
        try:
            res = book_odds(w, lr_all, horizon=a.horizon, targets=targets, keep_drift=a.keep_drift,
                            eightk=eightk, events_per_slot=eps, n_draws=a.draws)
        except BookRefused as ex:
            print(f"REFUSED {name}: {ex}")
            receipt["refused"][name] = str(ex)
            rc = 2
            continue
        receipt["books"][name] = res
        print(f"\n== {name}  cash={res['cash']:.0%}")
        for L, row in res["by_lookback"].items():
            print(f"  lookback {L} (bench {row['benchmark_proxy']}, abs sigma/day {row['sigma_daily_abs']:.2%})")
            for est in [k for k in row if k in ("normal", "windows", "block") or k.startswith("block+")
                        or k.endswith("raw_drift")]:
                print(f"    {est:<16} {_fmt(row[est], targets)}")
    if a.random_control and pool:
        receipt["random_control"] = random_control(pool, lr_all, n=a.random_control, targets=targets)
        rcx = receipt["random_control"]
        print(f"\n== random control: {rcx['n']} x 5x20% from {rcx['pool_size']} names; "
              f"median rel sd {rcx['sd_rel_median']:.1%}; P(beat) medians "
              + ", ".join(f"{k}: {v['median']:.3f}" for k, v in rcx["p_beat_normal"].items()))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"odds_{run_id}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)
    print(f"\nreceipt: {path}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
