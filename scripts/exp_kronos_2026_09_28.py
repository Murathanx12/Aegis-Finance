"""X1 (LANE X, 2026-09-28): Kronos zero-shot on our own survivorship-free panel.

A PRODUCT_EXPERIMENT, not a claim. One variant, no tuning, one stop.

QUESTION
  At month-end decision dates t, using ONLY bars dated <= t, does Kronos
  (NeoQuasar/Kronos-small, MIT, github.com/shiyu-coder/Kronos) forecast
  (a) the next-21-session realised volatility better than the trailing
      63-session volatility (QLIKE, rank correlation), and
  (b) the next-21-session return well enough that top-20 minus bottom-20 by
      forecast return, net of the band round trip, beats the panel's random
      portfolio and 12-1 momentum on the same 300 names and dates?

PRIORS STATED BEFORE THE RUN
  * 2026-09-22 (§59): price/volume features cannot rank at 21 sessions after
    costs on a survivorship-free panel. Kronos sees only price/volume.
  * Kronos pretraining data "extends up to June 2024" (arXiv:2508.02739), from
    45+ exchanges incl. NASDAQ. Any HOLD month <= 2024-06 is CONTAMINATED: the
    model may have trained on the very outcome. The verdict reads ONLY hold
    months >= 2024-07 (POST). PRE results are printed and never decide.

DECLARED DECISION RULE (POST hold months only)
  VOL beats prior    : mean(QLIKE_kronos - QLIKE_prior) < 0 with date-block t <= -2
  RANK beats random  : mean(long top-20 net - random net) > 0 with t >= 2
                       (L/S net spread and IC printed beside it)
  STOP: neither beats -> FAILED_VARIANT; no second variant, no tuning.

Runs in the SEPARATE venv `.venv_kronos` (torch + the cloned Kronos repo at
`.venv_kronos/Kronos`). Pure functions here import no torch so the project
suite can test them.

    .venv_kronos/Scripts/python.exe -m scripts.exp_kronos_2026_09_28 --phase post
    .venv_kronos/Scripts/python.exe -m scripts.exp_kronos_2026_09_28 --analyze-only --run-id ID
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ───────────────────────── constants (a script, not a service) ─────────────
DATA_DEEP = ROOT / "backend/data/optimus/prices_deep/bars.parquet"
DATA_DELISTED = ROOT / "backend/data/optimus/prices_deep/bars_delisted.parquet"
OUT_DIR = ROOT / "backend/data/optimus/experiments_2026-09-28"
KRONOS_REPO = ROOT / ".venv_kronos/Kronos"
KRONOS_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"

MODEL_ID = "NeoQuasar/Kronos-small"
TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
MAX_CONTEXT = 512
LOOKBACK = 400            # sessions of context fed to Kronos (400 + 21 <= 512)
HORIZON = 21
VOL_PRIOR_WIN = 63
N_NAMES = 300
K = 20
SAMPLES = 8               # sampled paths per name
BATCH = 8                 # names per GPU micro-batch (x SAMPLES sequences). Measured on the
                          # RTX 5060 8 GB: 8 names = 6.7 s (reserved 3.2 GB); 16 names = 607 s
                          # (reserved 9.2 GB > VRAM -> WDDM paging); 100 names spilled 28 GB to host.
TEMPERATURE = 1.0
TOP_P = 0.9
MIN_MDV = 2e7             # liquid = mid band or better (xs_ranker.liquidity_band)
MIN_PRICE = 5.0
SEED = 20260928
CUTOFF_LAST_TRAIN_MONTH = "2024-06"   # "pre-training data extends up to June 2024"
COST_BPS_BY_BAND = {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0}  # = xs_ranker
INDEX_PROXIES = frozenset({"SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "VOO"})
FREE_GB_REQUIRED = 40.0


# ───────────────────────── pure functions (tested) ──────────────────────────
def liquidity_band(mdv: Optional[float]) -> str:
    if mdv is None or not np.isfinite(mdv):
        return "small"
    if mdv >= 1e9:
        return "mega"
    if mdv >= 1e8:
        return "large"
    if mdv >= 2e7:
        return "mid"
    return "small"


def round_trip_cost(mdv: Optional[float]) -> float:
    """Round trip as a FRACTION (18 bps -> 0.0018)."""
    return COST_BPS_BY_BAND[liquidity_band(mdv)] / 1e4


def month_end_sessions(dates: Iterable) -> list:
    """The last trading session of each calendar month present in `dates`."""
    s = pd.Series(sorted(pd.DatetimeIndex(pd.unique(pd.DatetimeIndex(dates)))))
    return list(s.groupby(s.dt.to_period("M")).max())


def pit_slice(g: pd.DataFrame, t: pd.Timestamp, lookback: int) -> pd.DataFrame:
    """Bars of ONE symbol dated <= t, the last `lookback` of them. Never later."""
    g = g[g["date"] <= t]
    return g.iloc[-lookback:]


def forward_outcome(g: pd.DataFrame, t: pd.Timestamp, h: int = HORIZON) -> dict:
    """Return and realised daily log-return sd over the next h sessions after t.

    A name that stops trading inside the window is held to its last close (the
    delisting return itself is not in the panel; flagged `truncated`)."""
    g = g.sort_values("date")
    past = g[g["date"] <= t]
    fut = g[g["date"] > t].iloc[:h]
    if past.empty or fut.empty:
        return {"fwd_ret": float("nan"), "real_vol": float("nan"), "n_fwd": 0, "truncated": True}
    c0 = float(past["close"].iloc[-1])
    closes = np.concatenate([[c0], fut["close"].to_numpy(dtype=float)])
    lr = np.diff(np.log(closes))
    return {"fwd_ret": float(closes[-1] / c0 - 1.0),
            "real_vol": float(np.std(lr, ddof=1)) if len(lr) >= 10 else float("nan"),
            "n_fwd": int(len(fut)), "truncated": bool(len(fut) < h)}


def trailing_vol(closes, win: int = VOL_PRIOR_WIN) -> float:
    c = np.asarray(closes, dtype=float)[-(win + 1):]
    if len(c) < win + 1:
        return float("nan")
    return float(np.std(np.diff(np.log(c)), ddof=1))


def mom_12_1(closes) -> float:
    c = np.asarray(closes, dtype=float)
    if len(c) < 253:
        return float("nan")
    return float(c[-22] / c[-253] - 1.0)


def path_stats(last_close: float, paths) -> tuple:
    """paths: (S, H) sampled closes. -> (mean forecast return, forecast daily sd).

    The sd is the root-mean of each path's own variance (averaging the PATHS
    first, as the repo's `predict` does, would smooth the volatility away)."""
    p = np.asarray(paths, dtype=float)
    p = np.where(p > 0, p, np.nan)
    full = np.concatenate([np.full((p.shape[0], 1), float(last_close)), p], axis=1)
    lr = np.diff(np.log(full), axis=1)
    var = np.nanvar(lr, axis=1, ddof=1)
    ret = np.nanmean(p[:, -1] / float(last_close) - 1.0)
    return float(ret), float(np.sqrt(np.nanmean(var)))


def qlike(real_sd, fc_sd):
    """QLIKE on variances: r/f - log(r/f) - 1 >= 0, zero iff f == r. Robust to
    noise in the realised proxy (Patton 2011)."""
    r = np.asarray(real_sd, dtype=float) ** 2
    f = np.asarray(fc_sd, dtype=float) ** 2
    x = r / f
    return x - np.log(x) - 1.0


def spread_net(score, fwd, cost, k: int = K) -> dict:
    """Top-k long, bottom-k short, equal weight, each leg pays its round trip.

    Also the long-only top-k net and the sample's random-portfolio net (equal
    weight of all names minus their mean round trip: the expectation of a
    random-k draw)."""
    d = pd.DataFrame({"s": score, "r": fwd, "c": cost}).dropna()
    if len(d) < 2 * k:
        return {"ls_net": float("nan"), "long_net": float("nan"),
                "random_net": float("nan"), "n": len(d)}
    d = d.sort_values("s", kind="mergesort")
    top, bot = d.iloc[-k:], d.iloc[:k]
    long_net = top["r"].mean() - top["c"].mean()
    ls_net = (top["r"].mean() - bot["r"].mean()) - top["c"].mean() - bot["c"].mean()
    return {"ls_net": float(ls_net), "long_net": float(long_net),
            "random_net": float(d["r"].mean() - d["c"].mean()), "n": int(len(d))}


def series_summary(x) -> dict:
    """x indexed by HOLD month ('YYYY-MM'). Mean, SE, t, MDE (80% power, 5%
    two-sided = 2.8 SE), by year, leave-one-year-out, and the mean without the
    best 5 months (session-protocol item 11)."""
    x = pd.Series(x).dropna().astype(float)
    n = len(x)
    if n == 0:
        return {"n": 0}
    mean = float(x.mean())
    se = float(x.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    years = pd.Index([str(i)[:4] for i in x.index])
    by_year = {y: {"mean": float(v.mean()), "n": int(len(v))}
               for y, v in x.groupby(years)}
    loyo = {y: float(x[years != y].mean()) for y in by_year if (years != y).any()}
    wo5 = float(x.sort_values().iloc[:-5].mean()) if n > 5 else float("nan")
    ok = bool(np.isfinite(se) and se > 0)
    return {"n": n, "mean": mean, "se": se,
            "t": float(mean / se) if ok else float("nan"),
            "mde_80": float(2.8 * se) if ok else float("nan"),
            "median": float(x.median()), "share_positive": float((x > 0).mean()),
            "by_year": by_year, "leave_one_year_out": loyo,
            "loyo_worst": float(min(loyo.values())) if loyo else float("nan"),
            "mean_without_best_5": wo5}


def spearman(a, b) -> float:
    """Spearman rank correlation without scipy (`.venv_kronos` has none; on
    2026-09-28 pandas' method="spearman" imported it lazily and the finished
    26-date run died in the analysis step). Pairwise NaN drop, average ranks,
    Pearson on the ranks: the same number pandas returns."""
    d = pd.DataFrame({"a": np.asarray(a, dtype=float), "b": np.asarray(b, dtype=float)}).dropna()
    if len(d) < 2:
        return float("nan")
    return float(d["a"].rank().corr(d["b"].rank()))


def hold_month(t) -> str:
    return (pd.Timestamp(t) + pd.offsets.MonthBegin(1)).strftime("%Y-%m")


def is_post_cutoff(hm: str) -> bool:
    return hm > CUTOFF_LAST_TRAIN_MONTH


def sample_names(eligible, t, n: int = N_NAMES) -> list:
    """A deterministic draw per date, independent of any forecast."""
    rng = np.random.default_rng(SEED + int(pd.Timestamp(t).strftime("%Y%m")))
    el = sorted(eligible)
    if len(el) <= n:
        return el
    return sorted(rng.choice(el, size=n, replace=False).tolist())


def future_stamps(t, h: int = HORIZON) -> pd.DatetimeIndex:
    """Future timestamps from the business-day calendar, NOT the realised
    trading calendar (which is information from after t)."""
    return pd.bdate_range(pd.Timestamp(t) + pd.Timedelta(days=1), periods=h)


# ───────────────────────── panel ────────────────────────────────────────────
def load_panel() -> pd.DataFrame:
    cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
    a = pd.read_parquet(DATA_DEEP, columns=cols)
    b = pd.read_parquet(DATA_DELISTED, columns=cols)
    p = pd.concat([a, b], ignore_index=True)
    del a, b
    p = p.drop_duplicates(["symbol", "date"], keep="first")
    p = p[~p["symbol"].isin(INDEX_PROXIES)]
    for c in ["open", "high", "low", "close"]:
        p[c] = p[c].astype("float32")
    p["volume"] = p["volume"].astype("float64")
    return p.sort_values(["symbol", "date"]).reset_index(drop=True)


def build_date_universe(groups: dict, t) -> list:
    """Eligible names at t: traded on t, >= LOOKBACK sessions, mid band or
    better by 63-session median dollar volume, close >= $5."""
    out = []
    t64 = np.datetime64(pd.Timestamp(t))
    for sym, g in groups.items():
        dates = g["date"].to_numpy()
        i = int(np.searchsorted(dates, t64, side="right"))
        if i < LOOKBACK or dates[i - 1] != t64:
            continue
        c = g["close"].to_numpy()[:i]
        if c[-1] < MIN_PRICE:
            continue
        dv = c[-63:].astype(float) * g["volume"].to_numpy()[i - 63:i]
        mdv = float(np.median(dv))
        if mdv < MIN_MDV:
            continue
        out.append({"symbol": sym, "i": i, "mdv": mdv})
    return out


# ───────────────────────── Kronos (torch only here) ─────────────────────────
def _load_kronos():
    import os                                                       # noqa: PLC0415
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import torch                                                    # noqa: PLC0415
    sys.path.insert(0, str(KRONOS_REPO))
    from model import Kronos, KronosTokenizer                       # noqa: PLC0415
    tok = KronosTokenizer.from_pretrained(TOKENIZER_ID)
    mdl = Kronos.from_pretrained(MODEL_ID)
    dev = "cuda:0" if torch.cuda.is_available() else "cpu"
    tok = tok.to(dev)
    mdl = mdl.to(dev)
    tok.train(False)
    mdl.train(False)
    return torch, tok, mdl, dev


def kronos_paths(torch, tok, mdl, dev, xs, x_stamp, y_stamp, seed: int):
    """The repo's `auto_regressive_inference`, minus its final average over
    samples: returns (B, S, H, F) normalised sampled paths."""
    from model.kronos import sample_from_logits                     # noqa: PLC0415
    torch.manual_seed(seed)
    with torch.no_grad():
        B = xs.shape[0]
        S = SAMPLES
        x = torch.from_numpy(xs).float().to(dev).clamp(-5, 5)
        xst = torch.from_numpy(x_stamp).float().to(dev)
        yst = torch.from_numpy(y_stamp).float().to(dev)
        x = x.unsqueeze(1).repeat(1, S, 1, 1).reshape(B * S, x.size(1), x.size(2))
        xst = xst.unsqueeze(1).repeat(1, S, 1, 1).reshape(B * S, xst.size(1), xst.size(2))
        yst = yst.unsqueeze(1).repeat(1, S, 1, 1).reshape(B * S, yst.size(1), yst.size(2))
        tok0, tok1 = tok.encode(x, half=True)
        L = x.size(1)
        assert L + HORIZON <= MAX_CONTEXT
        pre = torch.cat([tok0, tok0.new_zeros(B * S, HORIZON)], dim=1)
        post = torch.cat([tok1, tok1.new_zeros(B * S, HORIZON)], dim=1)
        stamp = torch.cat([xst, yst], dim=1)
        for i in range(HORIZON):
            n = L + i
            s1_logits, ctx = mdl.decode_s1(pre[:, :n], post[:, :n], stamp[:, :n, :].contiguous())
            sp = sample_from_logits(s1_logits[:, -1, :], temperature=TEMPERATURE, top_k=0,
                                    top_p=TOP_P, sample_logits=True)
            s2_logits = mdl.decode_s2(ctx, sp)
            so = sample_from_logits(s2_logits[:, -1, :], temperature=TEMPERATURE, top_k=0,
                                    top_p=TOP_P, sample_logits=True)
            pre[:, n] = sp.squeeze(-1)
            post[:, n] = so.squeeze(-1)
        z = tok.decode([pre, post], half=True)
        z = z[:, -HORIZON:, :].reshape(B, S, HORIZON, z.size(-1))
        return z.float().cpu().numpy()


def _stamp(ts) -> np.ndarray:
    ts = pd.DatetimeIndex(ts)
    return np.stack([ts.minute, ts.hour, ts.weekday, ts.day, ts.month], axis=1).astype(np.float32)


def run_date(t, groups, kr, batch: int = BATCH) -> list:
    uni = build_date_universe(groups, t)
    by = {u["symbol"]: u for u in uni}
    names = sample_names(list(by), t)
    rows, xs, stats = [], [], []
    for s in names:
        g = groups[s]
        i = by[s]["i"]
        ctx = g.iloc[i - LOOKBACK:i]
        assert ctx["date"].iloc[-1] == t          # PIT: nothing after t
        closes = g["close"].to_numpy(dtype=float)[:i]
        x = ctx[["open", "high", "low", "close", "volume"]].to_numpy(dtype=np.float64)
        amt = x[:, 4] * x[:, :4].mean(axis=1)     # the repo's own `amount` rule
        x = np.concatenate([x, amt[:, None]], axis=1)
        if not np.isfinite(x).all():
            continue
        mu, sd = x.mean(axis=0), x.std(axis=0)
        xs.append(((x - mu) / (sd + 1e-5)).astype(np.float32))
        stats.append((mu, sd, _stamp(ctx["date"])))
        fo = forward_outcome(g, t)
        rows.append({"date": str(pd.Timestamp(t).date()), "hold_month": hold_month(t),
                     "symbol": s, "mdv": by[s]["mdv"], "band": liquidity_band(by[s]["mdv"]),
                     "cost": round_trip_cost(by[s]["mdv"]), "last_close": float(closes[-1]),
                     "prior_vol": trailing_vol(closes), "mom_12_1": mom_12_1(closes),
                     "n_eligible": len(by), **fo})
    if not rows:                                  # < LOOKBACK sessions of history anywhere
        return rows
    ys = _stamp(future_stamps(t))
    torch, tok, mdl, dev = kr
    for b0 in range(0, len(rows), batch):
        sl = slice(b0, b0 + batch)
        xb = np.stack(xs[sl])
        xst = np.stack([st[2] for st in stats[sl]])
        yst = np.repeat(ys[None], xb.shape[0], axis=0)
        z = kronos_paths(torch, tok, mdl, dev, xb, xst, yst,
                         seed=SEED + int(pd.Timestamp(t).strftime("%Y%m")) * 10 + b0)
        for j, r in enumerate(rows[sl]):
            mu, sd, _ = stats[b0 + j]
            close_paths = z[j, :, :, 3] * (sd[3] + 1e-5) + mu[3]
            fr, fv = path_stats(r["last_close"], close_paths)
            r["k_ret"], r["k_vol"] = fr, fv
        torch.cuda.empty_cache() if dev.startswith("cuda") else None
    return rows


# ───────────────────────── analysis ─────────────────────────────────────────
SUMMARY_COLS = ("qlike_kronos", "qlike_prior", "qlike_diff", "vol_rankcorr_kronos",
                "vol_rankcorr_prior", "ret_ic_kronos", "ret_ic_mom", "kronos_ls_net",
                "mom_ls_net", "kronos_long_net", "mom_long_net", "random_net",
                "kronos_long_minus_random", "mom_long_minus_random",
                "kronos_long_minus_mom_long", "scale_ratio_median")


def per_date_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ok = df[["real_vol", "prior_vol", "k_vol"]].gt(0).all(axis=1)
    df["q_k"] = np.nan
    df["q_p"] = np.nan
    df.loc[ok, "q_k"] = qlike(df.loc[ok, "real_vol"], df.loc[ok, "k_vol"])
    df.loc[ok, "q_p"] = qlike(df.loc[ok, "real_vol"], df.loc[ok, "prior_vol"])
    per = []
    for (d, hm), g in df.groupby(["date", "hold_month"]):
        v = g.dropna(subset=["q_k", "q_p"])
        k = spread_net(g["k_ret"], g["fwd_ret"], g["cost"])
        m = spread_net(g["mom_12_1"], g["fwd_ret"], g["cost"])
        per.append({"date": d, "hold_month": hm, "n": len(g),
                    "qlike_kronos": v["q_k"].mean(), "qlike_prior": v["q_p"].mean(),
                    "qlike_diff": (v["q_k"] - v["q_p"]).mean(),
                    "vol_rankcorr_kronos": spearman(v["k_vol"], v["real_vol"]),
                    "vol_rankcorr_prior": spearman(v["prior_vol"], v["real_vol"]),
                    "ret_ic_kronos": spearman(g["k_ret"], g["fwd_ret"]),
                    "ret_ic_mom": spearman(g["mom_12_1"], g["fwd_ret"]),
                    "kronos_ls_net": k["ls_net"], "kronos_long_net": k["long_net"],
                    "mom_ls_net": m["ls_net"], "mom_long_net": m["long_net"],
                    "random_net": k["random_net"],
                    "kronos_long_minus_random": k["long_net"] - k["random_net"],
                    "mom_long_minus_random": m["long_net"] - m["random_net"],
                    "kronos_long_minus_mom_long": k["long_net"] - m["long_net"],
                    "scale_ratio_median": float((v["k_vol"] / v["real_vol"]).median())
                    if len(v) else float("nan"),
                    "truncated": int(g["truncated"].sum())})
    return pd.DataFrame(per)


def decide(post: dict) -> dict:
    verdict = {"rule": "VOL beats if mean QLIKE diff < 0 with t <= -2; RANK beats if "
                       "mean(long top-20 net - random net) > 0 with t >= 2; POST only"}
    if not post.get("n_dates"):
        verdict["verdict"] = "NO_POST_DATES"
        return verdict
    qd, lr = post["qlike_diff"], post["kronos_long_minus_random"]
    vol_beats = bool(qd["mean"] < 0 and qd["t"] <= -2)
    rank_beats = bool(lr["mean"] > 0 and lr["t"] >= 2)
    won = [n for n, b in (("vol", vol_beats), ("rank", rank_beats)) if b]
    verdict.update({"vol_beats_prior": vol_beats, "rank_beats_random": rank_beats,
                    "verdict": "FAILED_VARIANT" if not won else "PARTIAL: " + ", ".join(won)})
    return verdict


def analyze(df: pd.DataFrame) -> dict:
    per = per_date_table(df)
    out = {}
    for phase, sub in (("POST", per[per["hold_month"].map(is_post_cutoff)]),
                       ("PRE_CONTAMINATED", per[~per["hold_month"].map(is_post_cutoff)])):
        if sub.empty:
            out[phase] = {"n_dates": 0}
            continue
        s = sub.set_index("hold_month")
        block = {"n_dates": int(len(sub)), "n_rows": int(sub["n"].sum()),
                 "hold_months": [str(sub["hold_month"].min()), str(sub["hold_month"].max())],
                 "truncated_rows": int(sub["truncated"].sum())}
        for c in SUMMARY_COLS:
            block[c] = series_summary(s[c])
        block["vol_rankcorr_diff"] = series_summary(s["vol_rankcorr_kronos"] - s["vol_rankcorr_prior"])
        out[phase] = block
    out["verdict"] = decide(out.get("POST", {}))
    out["per_date"] = per.to_dict(orient="records")
    return out


# ───────────────────────── main ─────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["post", "pre", "all"], default="post")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--max-dates", type=int, default=0)
    ap.add_argument("--pre-every", type=int, default=1, help="use every n-th pre date")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--batch", type=int, default=BATCH)
    a = ap.parse_args(argv)
    from backend.services import disk_guard as DG                   # noqa: PLC0415
    m = DG.require_free(FREE_GB_REQUIRED, "exp_kronos", path=OUT_DIR)
    print(f"free disk {m['free_bytes'] / DG.GB:.1f} GB", flush=True)
    run_id = a.run_id or datetime.now(timezone.utc).strftime("kronos_%Y%m%dT%H%M%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = OUT_DIR / f"x1_{run_id}_rows.jsonl"
    if not a.analyze_only:
        t0 = time.time()
        panel = load_panel()
        print(f"panel {len(panel):,} rows, {panel['symbol'].nunique():,} symbols, "
              f"{panel['date'].min().date()}..{panel['date'].max().date()}", flush=True)
        cal = pd.DatetimeIndex(sorted(panel["date"].unique()))
        groups = {s: g.reset_index(drop=True) for s, g in panel.groupby("symbol", sort=False)}
        del panel
        mes = [t for t in month_end_sessions(cal) if t.year >= 2017]
        mes = [t for t in mes if (cal > t).sum() >= HORIZON]   # whole hold must exist
        post = [t for t in mes if is_post_cutoff(hold_month(t))]
        pre = [t for t in mes if not is_post_cutoff(hold_month(t))][::-1][::a.pre_every][::-1]
        dates = {"post": post, "pre": pre, "all": post + pre}[a.phase]
        done = set()
        if rows_path.exists():
            for ln in rows_path.read_text(encoding="utf-8").splitlines():
                done.add(json.loads(ln)["date"])
        dates = [t for t in dates if str(t.date()) not in done]
        if a.max_dates:
            dates = dates[:a.max_dates]
        print(f"last session {cal[-1].date()}; {len(dates)} dates to run; loading model",
              flush=True)
        kr = _load_kronos()
        for t in dates:
            t1 = time.time()
            rows = run_date(t, groups, kr, batch=a.batch)
            with open(rows_path, "a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, default=float) + "\n")
            print(f"{t.date()} hold {hold_month(t)} n={len(rows)} {time.time()-t1:.0f}s "
                  f"(total {time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame([json.loads(l) for l in rows_path.read_text(encoding="utf-8").splitlines()])
    res = analyze(df)
    receipt = {
        "experiment": "X1 Kronos zero-shot, LANE X, 2026-09-28", "run_id": run_id,
        "licence": "PRODUCT_EXPERIMENT (no claim)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {"id": MODEL_ID, "tokenizer": TOKENIZER_ID, "licence": "MIT",
                  "repo": "github.com/shiyu-coder/Kronos", "repo_commit": KRONOS_COMMIT,
                  "pretraining_cutoff": "June 2024 (arXiv:2508.02739: 'The pre-training data "
                                        "for Kronos extends up to June 2024')"},
        "construction": {"lookback": LOOKBACK, "horizon": HORIZON, "names_per_date": N_NAMES,
                         "k": K, "samples": SAMPLES, "T": TEMPERATURE, "top_p": TOP_P,
                         "universe": "prices_deep bars + bars_delisted (survivorship-free); "
                                     "traded on t, >=400 sessions, 63d median $vol >= $20M, "
                                     "close >= $5, index ETFs excluded",
                         "future_timestamps": "business-day calendar, not realised sessions",
                         "costs": "xs_ranker band round trip per name per leg; no borrow fee",
                         "random_portfolio": "equal weight of the 300-name sample minus its "
                                             "mean round trip (= E[random-20 net])",
                         "vol_prior": "trailing 63-session sd of daily log returns",
                         "vol_target": "sd of the next 21 daily log returns",
                         "delisting": "held to last close; delisting return not in panel"},
        "priors": ["2026-09-22 §59: price/volume cannot rank at 21 sessions after costs "
                   "on a survivorship-free panel",
                   "hold months <= 2024-06 are CONTAMINATED (inside Kronos pretraining)"],
        "rows_file": str(rows_path.relative_to(ROOT)).replace("\\", "/"),
        "rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "n_rows": int(len(df)),
        **res,
    }
    rp = OUT_DIR / f"x1_{run_id}_receipt.json"
    DG.atomic_write_json(rp, receipt)
    v = res["verdict"]
    print(json.dumps({k: v.get(k) for k in ("vol_beats_prior", "rank_beats_random", "verdict")}),
          flush=True)
    print(f"receipt {rp}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
