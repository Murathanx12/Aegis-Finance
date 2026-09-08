"""LABOR DAY LAB — lane B, item B1. A SYNTHETIC KNOWN-ANSWER BATTERY FOR THE
WHOLE RESEARCH MACHINE.

    python -m scripts.labor_b1_known_answer_battery            # full battery
    python -m scripts.labor_b1_known_answer_battery --fast     # test-sized

WHY THIS EXISTS
===============
Every receipt in this repo is a statement about the WORLD made through an
INSTRUMENT. When the instrument says NOISE we have been assuming the world was
noisy. That assumption has never been tested end to end: `panel2_planted_worlds`
plants effects and measures RECOVERY of an IC, but it stops at one contrast on
one panel and never touches the four stages that actually decide what this repo
believes — `learner/inference` (deflation, power, MDE), `learner/evidence_memory`
(the state machine that promotes and refutes), and `learner/allocator` (the thing
that turns a belief into a weight).

So: four synthetic worlds whose answers are KNOWN BY CONSTRUCTION, pushed through
`dataset-shaped panel -> models -> evaluate -> inference -> evidence_memory ->
allocator` with the REAL code at every stage, and a required outcome declared for
each before the run:

  (i)   `linear`  — a planted linear cross-sectional edge on ONE named carrier.
  (ii)  `regime`  — the SAME carrier, live only inside a market-volatility state.
  (iii) `graph`   — customer return in month j -> supplier excess in month j+1,
                    carried ONLY by `learner/features_graph`'s own columns.
  (iv)  `null`    — the identical panel with the alpha term set to zero.

REQUIRED OUTCOMES (declared here, adjudicated by the run, not by the reader):
  * (i)-(iii): the best cell recovers the effect with the CORRECT SIGN and a
    family-corrected p < 0.05 over the whole 12-cell family.
  * (iv): the verdict word is NOISE — not CANNOT DETERMINE — which requires the
    battery to be POWERED, and the evidence memory ends at REFUTED.
  * the evidence memory's state for each world is the declared one.
  * the allocator gives the null world ZERO weight and parks the residual in the
    benchmark.

ANY MISS IS A DEFECT IN THE MACHINE, NOT IN THE WORLD. The planted effect is
sized ABOVE the machine's own MDE on this tape (both numbers are printed side by
side in the receipt) so a miss cannot be explained away as "underpowered".

WHAT IS SYNTHETIC AND WHAT IS REAL — stated plainly, because a known-answer
battery that quietly reimplements the machine tests nothing:

  REAL (imported and called):  learner.dataset (schema + walk_forward_splits),
    learner.models.fit_predict / fit_predict_proba, learner.evaluate.book,
    learner.inference.full_report (DSR / SPA / PBO / power / MDE),
    learner.features_graph.load_edges / relation_table / build / attach,
    learner.evidence_memory.observe / state_of,
    learner.allocator.utility_of / _allocate,
    scripts.weekend_lab_jobs.verdict_from (the verdict vocabulary).

  SYNTHETIC (generated here):  the panel itself, the edge file, and — for the
    graph world only — `features_graph.monthly_returns`, which is monkeypatched
    to return the synthetic panel's own monthly returns instead of reading CRSP.
    Nothing else in `features_graph` is replaced: `load_edges`, `relation_table`,
    the liveness rule, the aggregation and `attach` all run as written.

  NEVER TOUCHED: the real `evidence_memory.jsonl`. `EM.STORE` is redirected to a
    scratch file for the duration of the run and restored afterwards; the real
    store is neither read nor appended to. Same for the graph feature parquet —
    `features_graph.build` returns a frame, and `save()` is never called.

LICENCE: PRODUCT_EXPERIMENT (a synthetic-world instrument test; it is not market
evidence and every receipt says so).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import allocator as AL                     # noqa: E402
from learner import dataset as D                        # noqa: E402
from learner import evaluate as EV                      # noqa: E402
from learner import evidence_memory as EM               # noqa: E402
from learner import features_graph as FG                # noqa: E402
from learner import inference as INF                    # noqa: E402
from learner import models as M                         # noqa: E402
from scripts import weekend_lab_jobs as WLJ             # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"
RECEIPT = OUT_DIR / "B1_known_answer_battery.json"
FAST_RECEIPT = OUT_DIR / "B1_known_answer_battery_fast.json"

SEED = 20260907
WORLDS = ("linear", "regime", "graph", "null")

#: The carrier for the linear and regime worlds. A REAL panel column name, so
#: the model has to find it among the other 48 rather than among two.
CARRIER = "mom_12_1"

#: The graph world's carrier. `features_graph` builds this column itself from
#: the synthetic edge file; nothing in this script writes it.
GRAPH_CARRIER = "graph_cust_mom_1m_ew"

#: Model kinds run per world. `mlp` is omitted on purpose and the omission is
#: stated: sklearn's MLP over 20 expanding folds x 4 worlds is ~40 minutes on
#: this machine for an arm that adds no new question to a known-answer test.
KINDS = ("ridge", "lgbm", "lgbm_clf")

#: Book construction. EQUAL weight is the primary: the alpha is planted
#: independent of market cap, so a value-weighted book would mix the recovery
#: question with a size question that was never asked.
BOOK_K = 50
BOOK_WEIGHT = "ew"
COST_BPS = EV.COST_BPS_PER_SIDE

#: Eras for a 1999-2024 panel. `evaluate.ERAS` is hard-coded to 2016-2024 and
#: would silently report three eras covering the last nine years of a
#: twenty-six-year panel (recorded as a finding in the receipt, not repaired
#: here — `evaluate.py` is not this lane's file).
def eras_for(years: list[int]) -> dict[str, tuple[int, int]]:
    ys = sorted(set(years))
    if len(ys) < 3:
        return {f"{ys[0]}-{ys[-1]}": (ys[0], ys[-1])} if ys else {}
    cuts = np.array_split(np.array(ys), 3)
    return {f"{c[0]}-{c[-1]}": (int(c[0]), int(c[-1])) for c in cuts if len(c)}


# ─────────────────────────────────────────────────────────── the synthetic panel


class Cfg:
    """Every knob in one object so the receipt can print the world it tested."""

    def __init__(self, fast: bool = False):
        self.fast = fast
        self.n_names = 60 if fast else 250
        self.start_year = 1999
        self.end_year = 2008 if fast else 2024
        self.test_years = ([2006, 2007, 2008] if fast
                           else list(range(2005, 2025)))
        self.kinds = KINDS
        self.worlds = ("linear", "null") if fast else WORLDS
        self.idio_sd = 0.08          # monthly idiosyncratic sd of a name
        self.mkt_mu = 0.007
        self.mkt_sd = 0.045
        # Planted alpha scale, in monthly return units per cross-sectional sd
        # of the carrier. Calibrated (see `oracle_effect`) so the ORACLE book's
        # annualised excess is several times the machine's own MDE.
        self.alpha_scale = 0.012
        self.regime_share = 0.35     # share of months the regime state is live
        # The regime world is live in only ~35% of months, so at a common
        # scale its POOLED effect would sit near the MDE and a miss could be
        # blamed on power. The in-state effect is multiplied up so the pooled
        # effect clears the MDE by the same margin the linear world does.
        self.regime_alpha_multiplier = 2.5
        self.n_customers = 4         # out-edges per subject in the graph world
        self.seed = SEED

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _month_index(cfg: Cfg) -> pd.PeriodIndex:
    return pd.period_range(f"{cfg.start_year}-01", f"{cfg.end_year}-12", freq="M")


def _xs_z(v: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score of one month's vector. Population sd, like the
    rest of the repo's per-month z helpers."""
    sd = float(np.std(v))
    return (v - float(np.mean(v))) / (sd if sd > 0 else 1.0)


def _xs_rank(v: np.ndarray) -> np.ndarray:
    """Within-month percentile rank in [0, 1] — the `__xs` convention."""
    order = np.argsort(np.argsort(v))
    return order / max(len(v) - 1, 1)


def build_world(cfg: Cfg, world: str) -> tuple[pd.DataFrame, dict]:
    """One dataset-shaped panel for one world. The same seed for every world,
    so the four differ ONLY in the alpha term — which is what makes the null a
    matched control rather than a different experiment."""
    rng = np.random.default_rng(cfg.seed)
    months = _month_index(cfg)
    n_m, n_n = len(months), cfg.n_names
    permnos = np.arange(90000, 90000 + n_n, dtype="int64")

    # Features: AR(1) in the name dimension so a carrier is persistent, which
    # is what makes an expanding-window fit meaningful.
    base_cols = list(D.FEATURES_CONTINUOUS)
    F = {}
    for c in base_cols:
        x = rng.standard_normal((n_m, n_n))
        for j in range(1, n_m):
            x[j] = 0.7 * x[j - 1] + math.sqrt(1 - 0.7 ** 2) * x[j]
        F[c] = x

    mkt = cfg.mkt_mu + cfg.mkt_sd * rng.standard_normal(n_m)
    # A market-volatility STATE: persistent, recurring, and knowable at j.
    hi_vol = np.abs(mkt) > np.quantile(np.abs(mkt), 1.0 - cfg.regime_share)

    eps = cfg.idio_sd * rng.standard_normal((n_m, n_n))
    market_cap = np.exp(rng.normal(21.0, 1.2, size=n_n))

    # ---- the alpha term: the ONLY difference between the four worlds --------
    alpha = np.zeros((n_m, n_n))
    carrier_z = np.vstack([_xs_z(F[CARRIER][j]) for j in range(n_m)])
    planted_note = ""
    if world == "linear":
        alpha[:-1] = cfg.alpha_scale * carrier_z[:-1]
        planted_note = (f"excess[j+1] += {cfg.alpha_scale} * xs_z({CARRIER}[j]) "
                        "on every month")
    elif world == "regime":
        alpha[:-1] = (cfg.alpha_scale * cfg.regime_alpha_multiplier
                      * carrier_z[:-1] * hi_vol[:-1, None].astype(float))
        planted_note = (f"excess[j+1] += "
                        f"{cfg.alpha_scale * cfg.regime_alpha_multiplier:.4f}"
                        f" * xs_z({CARRIER}[j]) "
                        f"ONLY when |market return[j]| is in the top "
                        f"{cfg.regime_share:.0%} of months; zero otherwise")
    elif world == "null":
        planted_note = "no alpha term at all — the matched control"

    # ---- returns. The graph world needs them month by month ----------------
    cust_of: dict[int, list[int]] = {}
    if world == "graph":
        for i in range(n_n):
            pool = [x for x in range(n_n) if x != i]
            cust_of[i] = list(rng.choice(pool, size=cfg.n_customers,
                                         replace=False))
        planted_note = (f"excess[j+1] += {cfg.alpha_scale} * xs_z(mean return "
                        f"of the name's {cfg.n_customers} CUSTOMERS in month j)"
                        " — carried only by features_graph's own columns")

    ret = np.zeros((n_m, n_n))       # total return of name i in month j
    cust_mean = np.zeros((n_m, n_n))
    for j in range(n_m):
        if world == "graph" and j > 0:
            cm = np.array([ret[j - 1, cust_of[i]].mean() for i in range(n_n)])
            cust_mean[j - 1] = cm
            alpha[j] = cfg.alpha_scale * _xs_z(cm)
        ret[j] = mkt[j] + alpha[j] + eps[j]

    w = market_cap / market_cap.sum()
    mkt_vw = ret @ w
    excess = ret - mkt_vw[:, None]

    # ---- assemble the dataset-shaped frame ---------------------------------
    rows = {
        "permno": np.tile(permnos, n_m - 1),
        "month": np.repeat([str(m) for m in months[:-1]], n_n),
        "entry_date": np.repeat(
            [months[j].to_timestamp(how="end").normalize() + pd.Timedelta(days=1)
             for j in range(n_m - 1)], n_n),
        "market_cap": np.tile(market_cap, n_m - 1),
        "vintage": np.repeat(
            [months[j].to_timestamp(how="end").normalize()
             for j in range(n_m - 1)], n_n),
    }
    for c in base_cols:
        rows[c] = F[c][:-1].reshape(-1)
    df = pd.DataFrame(rows)
    df["entry_date"] = pd.to_datetime(df["entry_date"])

    # ranked (`__xs`) columns, computed the way the real builder computes them
    for c in D.RANKED:
        col = np.vstack([_xs_rank(F[c][j]) for j in range(n_m - 1)])
        df[D.ranked_name(c)] = col.reshape(-1)
    df["split_prior_year"] = 0.0
    df["sector_code"] = np.tile(np.arange(n_n) % 10, n_m - 1).astype(float)
    df["band_code"] = np.tile(np.arange(n_n) % 4, n_m - 1).astype(float)

    # targets: month j's row is graded on month j+1's realised return
    fwd = ret[1:].reshape(-1)
    df["fwd_1m"] = fwd
    df["mkt_vw_1m"] = np.repeat(mkt_vw[1:], n_n)
    df["mkt_ew_1m"] = np.repeat(ret[1:].mean(axis=1), n_n)
    df["excess_vw_1m"] = excess[1:].reshape(-1)
    df["excess_ew_1m"] = (ret[1:] - ret[1:].mean(axis=1)[:, None]).reshape(-1)
    df["prior_1m"] = 0.0
    df["resid_vw_1m"] = df["excess_vw_1m"] - df["prior_1m"]
    df["resid_ew_1m"] = df["excess_ew_1m"] - df["prior_1m"]
    df["pos_vw_1m"] = (df["excess_vw_1m"] > 0).astype(float)
    df["mat_date_1m"] = np.repeat(
        [months[j + 1].to_timestamp(how="end").normalize()
         for j in range(n_m - 1)], n_n)
    df["mat_date_1m"] = pd.to_datetime(df["mat_date_1m"])
    # the TRUE alpha, kept for the oracle only. Never a feature, never a target.
    df["__true_alpha"] = alpha[1:].reshape(-1)

    meta = {
        "world": world,
        "planted": planted_note,
        "carrier": (GRAPH_CARRIER if world == "graph"
                    else (CARRIER if world != "null" else None)),
        "n_rows": int(len(df)),
        "n_names": n_n,
        "n_months": int(n_m - 1),
        "months": [str(months[0]), str(months[-2])],
        "regime_months": int(hi_vol.sum()) if world == "regime" else None,
        "idio_sd_monthly": cfg.idio_sd,
        "alpha_scale": cfg.alpha_scale,
    }
    extra = {"cust_of": cust_of, "ret": ret, "months": months,
             "permnos": permnos, "hi_vol": hi_vol}
    return df, {"meta": meta, "extra": extra}


# ────────────────────────────────────────────────── the graph world's features


def synthetic_edges(cfg: Cfg, cust_of: dict, permnos: np.ndarray,
                    months: pd.PeriodIndex, path: Path) -> dict:
    """An edge file in `features_graph.EDGE_COLUMNS` shape, re-filed every year
    so the module's own 730-day liveness rule keeps every edge alive."""
    recs = []
    n = len(permnos)
    rng = np.random.default_rng(cfg.seed + 7)
    # DECOY RELATIONS, and they are the point. `features_graph` builds four
    # relation classes and REFUSES a build in which any of them is empty
    # everywhere (measured: it refused this battery's first edge file, which
    # carried customers only — the guard works). So the graph world ships
    # competitors and shared-technology partners too. The planted propagation
    # runs ONLY through the customer channel; the other three classes are
    # decoys the model has to reject.
    comp_of = {i: list(rng.choice([x for x in range(n) if x != i], size=2,
                                  replace=False)) for i in range(n)}
    assoc_of = {i: list(rng.choice([x for x in range(n) if x != i], size=2,
                                   replace=False)) for i in range(n)}
    for year in range(cfg.start_year, cfg.end_year + 1):
        fd = pd.Timestamp(f"{year}-01-15")
        for i, custs in cust_of.items():
            for c in custs:
                recs.append({
                    "subject_permno": int(permnos[i]),
                    "counterparty_permno": int(permnos[c]),
                    "filing_date": fd, "date": fd + pd.Timedelta(days=30),
                    # "B is our customer" -> subject is the SUPPLIER, and the
                    # feature `graph_cust_mom_1m_ew` is the mean return of the
                    # subject's customers. That is the planted channel.
                    "type": "customer", "direction": "out",
                    "confidence": 0.9, "same_sector": False,
                })
            for c in comp_of[i]:
                recs.append({
                    "subject_permno": int(permnos[i]),
                    "counterparty_permno": int(permnos[c]),
                    "filing_date": fd, "date": fd + pd.Timedelta(days=30),
                    "type": "competitor", "direction": "mutual",
                    "confidence": 0.8, "same_sector": True})
            for c in assoc_of[i]:
                recs.append({
                    "subject_permno": int(permnos[i]),
                    "counterparty_permno": int(permnos[c]),
                    "filing_date": fd, "date": fd + pd.Timedelta(days=30),
                    "type": "shared_technology", "direction": "mutual",
                    "confidence": 0.6, "same_sector": False})
    e = pd.DataFrame.from_records(recs)
    path.parent.mkdir(parents=True, exist_ok=True)
    e.to_parquet(path, index=False)
    return {"path": str(path), "rows": int(len(e)),
            "subjects": int(e["subject_permno"].nunique()),
            "types": {k: int(v) for k, v in e["type"].value_counts().items()},
            "planted_channel": "customer only; competitor and "
                               "shared_technology are decoys",
            "filing_years": [cfg.start_year, cfg.end_year]}


def attach_graph_features(cfg: Cfg, df: pd.DataFrame, extra: dict,
                          edge_path: Path) -> tuple[pd.DataFrame, dict, dict]:
    """Run the REAL `features_graph.build` with only `monthly_returns` replaced."""
    ret, months, permnos = extra["ret"], extra["months"], extra["permnos"]
    long = pd.DataFrame({
        "permno": np.tile(permnos, len(months)),
        "month": np.repeat(list(months), len(permnos)),
        "mret": ret.reshape(-1),
    })
    long["thin_month"] = False

    def _fake_monthly_returns(pn, start_year, end_year, verbose=True):
        want = set(int(p) for p in pn)
        out = long[long["permno"].isin(want)
                   & (long["month"].apply(lambda m: start_year <= m.year <= end_year))]
        return out.reset_index(drop=True)

    real = FG.monthly_returns
    FG.monthly_returns = _fake_monthly_returns
    try:
        feats, greceipt = FG.build(edges_path=edge_path, verbose=False)
    finally:
        FG.monthly_returns = real
    joined, note = FG.attach(df, feats=feats)
    return joined, greceipt, note


# ─────────────────────────────────────────────────────────── running one cell


def run_cell(cfg: Cfg, df: pd.DataFrame, feature_cols: list[str],
             kind: str) -> dict | None:
    """One (world, model) cell: walk-forward fit, one prediction column, one
    book, one monthly paired-excess series. Real `models` and real `evaluate`."""
    preds, idxs = [], []
    metas = []
    for year, tr, te in D.walk_forward_splits(df, cfg.test_years, 1,
                                              min_train_months=24):
        train, test = df.loc[tr], df.loc[te]
        if kind == M.CLASSIFIER:
            p, meta = M.fit_predict_proba(train, test, feature_cols, 1)
        else:
            p, meta = M.fit_predict(kind, "raw", train, test, feature_cols, 1)
        preds.append(np.asarray(p, dtype="float64"))
        idxs.append(te)
        metas.append({"year": year, "n_train": meta.get("n_train")})
    if not preds:
        return None
    oos = df.loc[np.concatenate(idxs)].copy()
    oos["pred"] = np.concatenate(preds)
    b = EV.book(oos, "pred", k=min(BOOK_K, cfg.n_names // 4),
                weight=BOOK_WEIGHT, cost_bps=COST_BPS,
                return_series=True, with_risk=True)
    s = b.pop("_series")
    spread = (s["net"] - s["market"]).dropna()
    ic = EV.rank_ic(oos, "pred", "excess_vw_1m")
    return {"kind": kind, "folds": metas, "book": b,
            "rank_ic": ic, "spread": spread, "net": s["net"],
            "n_oos_rows": int(len(oos))}


def oracle_effect(cfg: Cfg, df: pd.DataFrame,
                  world_is_null: bool = False) -> dict:
    """The PLANTED effect, measured the same way the machine measures its own:
    the book a perfect ranker would have run over exactly the test years."""
    if world_is_null:
        return {"annualised_excess": 0.0, "t_stat_paired_vs_market": None,
                "months": None, "mean_monthly_excess": 0.0,
                "basis": ("NO alpha was planted. A book ranked on a constant "
                          "is a tie-break ordering, not an oracle, and quoting "
                          "its excess would invent a planted effect that does "
                          "not exist.")}
    mask = ((df["entry_date"] >= pd.Timestamp(f"{min(cfg.test_years)}-01-01"))
            & (df["entry_date"] < pd.Timestamp(f"{max(cfg.test_years) + 1}-01-01")))
    o = df.loc[mask].copy()
    o["pred"] = o["__true_alpha"]
    b = EV.book(o, "pred", k=min(BOOK_K, cfg.n_names // 4), weight=BOOK_WEIGHT,
                cost_bps=COST_BPS, return_series=True)
    s = b.pop("_series")
    sp = (s["net"] - s["market"]).dropna()
    return {"annualised_excess": b.get("annualised_excess"),
            "t_stat_paired_vs_market": b.get("t_stat_paired_vs_market"),
            "months": b.get("months"),
            "mean_monthly_excess": round(float(sp.mean()), 6),
            "basis": ("a book ranked on the TRUE planted alpha over the test "
                      "years, at the same k, weight and cost as every measured "
                      "cell. This is the planted effect in the units the MDE is "
                      "quoted in.")}


# ────────────────────────────────────────────────── multiplicity + the verdict


def _two_sided_p(t: float, n: int) -> float:
    """Normal approximation, matching `inference`'s own `_ncdf` convention."""
    return float(2.0 * (1.0 - INF._ncdf(abs(t))))


def holm_bh(pvals: dict[str, float]) -> dict:
    """Holm (EXPORT) and Benjamini-Hochberg (SCREEN) over one family. CANON §63."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    holm, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        holm[k] = round(running, 8)
    bh, prev = {}, 1.0
    for i in range(m - 1, -1, -1):
        k, p = items[i]
        prev = min(prev, min(1.0, p * m / (i + 1)))
        bh[k] = round(prev, 8)
    return {"family_size": m, "holm": holm, "bh_fdr": bh,
            "family_max_p": round(max(pvals.values()), 8) if pvals else None}


def era_block(spread: pd.Series, eras: dict) -> dict:
    """The three-era table `evidence_memory` reads to decide REGIME_SPECIFIC."""
    idx = pd.PeriodIndex(pd.to_datetime(spread.index.astype(str)), freq="M")
    means, ts = {}, {}
    for name, (lo, hi) in eras.items():
        sub = spread[(idx.year >= lo) & (idx.year <= hi)]
        if len(sub) < 6:
            continue
        means[name] = round(float(sub.mean()), 6)
        sd = float(sub.std(ddof=1))
        ts[name] = round(float(sub.mean() / sd * math.sqrt(len(sub))), 3) if sd > 0 else None
    pos = sum(1 for v in means.values() if v > 0)
    return {"era_means": means, "era_t": ts,
            "eras_measured": len(means), "eras_with_a_positive_mean": pos,
            "holds_in_2_of_3": bool(pos >= 2 and len(means) >= 3),
            "same_sign_in_2_of_3": bool(pos >= 2 or (len(means) - pos) >= 2)}


# ─────────────────────────────────────────────────────────────── the battery


def run_battery(cfg: Cfg) -> dict:
    t0 = time.time()
    scratch = Path(tempfile.mkdtemp(prefix="labor_b1_"))
    inputs_opened: list[dict] = []

    def _stamp(p: Path, why: str) -> None:
        try:
            st = p.stat()
            inputs_opened.append({"path": str(p), "bytes": st.st_size,
                                  "mtime_utc": datetime.fromtimestamp(
                                      st.st_mtime, timezone.utc).isoformat(
                                          timespec="seconds"), "why": why})
        except OSError:
            inputs_opened.append({"path": str(p), "bytes": None,
                                  "mtime_utc": None, "why": why + " (ABSENT)"})

    for mod in (D, M, EV, INF, EM, AL, FG):
        _stamp(Path(mod.__file__), f"machine stage: {mod.__name__}")

    base_cols = D.feature_columns()
    worlds: dict[str, dict] = {}
    cells: dict[str, dict] = {}

    for world in cfg.worlds:
        print(f"\n=== world {world} ===", flush=True)
        df, built = build_world(cfg, world)
        meta, extra = built["meta"], built["extra"]
        cols = list(base_cols)
        if world == "graph":
            ep = scratch / "synthetic_edges.parquet"
            meta["edges"] = synthetic_edges(cfg, extra["cust_of"],
                                            extra["permnos"], extra["months"], ep)
            _stamp(ep, "synthetic edge file (generated by this run)")
            df, greceipt, gnote = attach_graph_features(cfg, df, extra, ep)
            df = df.sort_index()
            meta["features_graph_receipt"] = {
                k: greceipt.get(k) for k in
                ("version", "source", "source_rows", "rows", "permnos",
                 "non_null_rate", "relations")}
            meta["features_graph_join"] = gnote
            cols += [c for c in FG.FEATURES if c in df.columns]
        meta["n_features_offered"] = len(cols)
        meta["oracle"] = oracle_effect(cfg, df, world_is_null=(world == "null"))

        world_cells = {}
        for kind in cfg.kinds:
            t1 = time.time()
            res = run_cell(cfg, df, cols, kind)
            if res is None:
                print(f"  {kind}: NO FOLDS", flush=True)
                continue
            world_cells[kind] = res
            cells[f"{world}::{kind}"] = res
            b = res["book"]
            print(f"  {kind:9s} ann.excess {b.get('annualised_excess')!s:>8} "
                  f"t {b.get('t_stat_paired_vs_market')!s:>7} "
                  f"IC {res['rank_ic'].get('mean_ic')!s:>8} "
                  f"({time.time()-t1:.0f}s)", flush=True)
        worlds[world] = {"meta": meta, "cells": list(world_cells)}

    # ---- the family: every cell, one multiplicity correction ---------------
    lengths = {k: len(v["spread"]) for k, v in cells.items()}
    pvals, tstats = {}, {}
    for k, v in cells.items():
        sp = v["spread"]
        sd = float(sp.std(ddof=1))
        t = float(sp.mean() / sd * math.sqrt(len(sp))) if sd > 0 else 0.0
        tstats[k] = round(t, 4)
        pvals[k] = _two_sided_p(t, len(sp))
    fam = holm_bh(pvals)

    years = sorted({int(str(m)[:4]) for k in cells
                    for m in cells[k]["spread"].index})
    eras = eras_for(years)

    # ---- per-cell inference through the REAL module ------------------------
    family_series = {k: v["spread"].to_numpy(dtype="float64")
                     for k, v in cells.items()}
    same_length = len(set(lengths.values())) == 1
    results: dict[str, dict] = {}
    for k, v in cells.items():
        sp = v["spread"]
        inf = INF.full_report(
            sp.to_numpy(dtype="float64"),
            family=family_series if same_length else None,
            paired_excess={k: sp.to_numpy(dtype="float64")},
            n_trials=len(cells), seed=cfg.seed)
        er = era_block(sp, eras)
        # X5 (2026-09-07): the family-corrected p travels INTO the verdict.
        # Without it `verdict_from` has only NOVEL or NOISE for a
        # self-resolved arm, and this battery's own planted edge at Holm
        # 0.01543 read NOISE.
        verdict = WLJ.verdict_from(inf, er, holm_p=fam["holm"][k])
        results[k] = {
            "t": tstats[k], "p_raw": round(pvals[k], 8),
            "p_holm": fam["holm"][k], "p_bh_fdr": fam["bh_fdr"][k],
            "annualised_excess": v["book"].get("annualised_excess"),
            "mean_monthly_excess": v["book"].get("mean_monthly_excess"),
            "months": int(len(sp)),
            "rank_ic": v["rank_ic"].get("mean_ic"),
            "rank_ic_t": v["rank_ic"].get("t_stat"),
            "rank_ic_months": v["rank_ic"].get("months"),
            "mde_annual_excess_at_t2": inf["power"].get(
                "mde_annual_excess_at_t_target"),
            "powered": inf["power"].get("powered"),
            "years_needed_for_t2": inf["power"].get("years_needed_for_t2"),
            "years_observed": inf["power"].get("years_observed"),
            "dsr": (inf.get("deflated_sharpe") or {}).get("dsr"),
            "spa_p": (inf.get("spa") or {}).get("p_spa_consistent"),
            "pbo": (inf.get("pbo") or {}).get("pbo"),
            "eras": er,
            "verdict": verdict,
        }

    # ---- the evidence memory, on a REDIRECTED store -------------------------
    mem = evidence_pass(cfg, results, scratch)

    # ---- the allocator, on synthetic sleeves built from the measured numbers
    alloc = allocator_pass(cfg, results)

    # ---- adjudication -------------------------------------------------------
    adj = adjudicate(cfg, worlds, results, mem, alloc)

    receipt = {
        "item": "LABOR_DAY_LAB_2026-09-07 / lane B / B1",
        "title": "synthetic known-answer battery for the whole research machine",
        "licence": "PRODUCT_EXPERIMENT",
        "mode": "SYNTHETIC_WORLD — NOT MARKET EVIDENCE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "argv": list(sys.argv),
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "config": cfg.as_dict(),
        "inputs_opened": inputs_opened,
        "machine_stages_exercised": [
            "learner.dataset.feature_columns / walk_forward_splits",
            "learner.features_graph.load_edges / relation_table / build / attach",
            "learner.models.fit_predict / fit_predict_proba",
            "learner.evaluate.book / rank_ic",
            "learner.inference.full_report (DSR, SPA, PBO, power, MDE)",
            "scripts.weekend_lab_jobs.verdict_from",
            "learner.evidence_memory.observe / state_of (REDIRECTED store)",
            "learner.allocator.utility_of / _allocate",
        ],
        "what_is_synthetic": [
            "the panel (features, returns, market, caps)",
            "the market-graph edge file",
            "features_graph.monthly_returns (monkeypatched for the graph world "
            "ONLY; every other function in that module runs as written)",
        ],
        "safety": {
            "real_evidence_memory_touched": False,
            "evidence_store_redirected_to": mem["store_path"],
            "graph_feature_parquet_written": False,
            "llm_calls": 0, "llm_spend_usd": 0.00,
        },
        "eras": eras,
        "worlds": {w: v["meta"] for w, v in worlds.items()},
        "family": {"cells": sorted(cells), "size": fam["family_size"],
                   "family_max_p": fam["family_max_p"],
                   "correction": "Holm (export) and BH-FDR (screen), CANON §63",
                   "pbo_computed_over": ("the whole family; all cells share a "
                                         "length" if same_length else
                                         "NOT COMPUTED — cells differ in length"),
                   "cell_months": lengths},
        "results": results,
        "evidence_memory": mem,
        "allocator": alloc,
        "adjudication": adj,
        "findings": adj["findings"],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    return receipt


# ─────────────────────────────────────────────────────── evidence + allocator


def evidence_pass(cfg: Cfg, results: dict, scratch: Path) -> dict:
    """Write every cell as a REAL `evidence_memory.observe` row, into a scratch
    store, then read each world's state back through the REAL `state_of`."""
    store = scratch / "evidence_memory.jsonl"
    real_store, real_dir = EM.STORE, EM.STORE_DIR
    EM.STORE, EM.STORE_DIR = store, scratch
    rows_by_world: dict[str, list[dict]] = {}
    try:
        for cell, r in results.items():
            world, kind = cell.split("::")
            row = EM.observe(
                f"B1_synthetic_{world}", cell,
                n_months=r["months"], sharpe=None,
                dsr=r["dsr"], spa_p=r["spa_p"], pbo=r["pbo"],
                verdict=r["verdict"], powered=r["powered"],
                years_needed_for_t2=r["years_needed_for_t2"],
                years_observed=r["years_observed"],
                eras=r["eras"],
                gross_beats_market=bool((r["annualised_excess"] or 0) > 0),
                net_beats_market=bool((r["annualised_excess"] or 0) > 0),
                job="labor_b1_known_answer_battery", run="B1", variant=kind,
                note="SYNTHETIC WORLD — not market evidence")
            rows_by_world.setdefault(world, []).append(row)
        states = {w: EM.state_of(rows) for w, rows in rows_by_world.items()}
    finally:
        EM.STORE, EM.STORE_DIR = real_store, real_dir
    return {"store_path": str(store),
            "real_store_untouched": str(real_store),
            "states": {w: {k: s[k] for k in
                           ("state", "why", "distinct_observations",
                            "passes_clearing_the_bar", "powered_passes",
                            "one_era_only_passes")}
                       for w, s in states.items()}}


def _sleeve(name: str, e: float, cvar: float, costs: float, unc: float,
            note: str) -> dict:
    return {"name": name, "gate": "DEPLOYABLE",
            "components": {
                "e_excess": AL.definition(e, note),
                "cvar": AL.definition(cvar, "measured max drawdown of the "
                                            "synthetic book"),
                "costs": AL.definition(costs, "measured cost line at "
                                              f"{COST_BPS} bps a side"),
                "uncertainty": AL.definition(unc, "the machine's own MDE at "
                                                  "t = 2 on this tape"),
            },
            "notes": [note]}


def allocator_pass(cfg: Cfg, results: dict) -> dict:
    """Build one sleeve per world from the MEASURED numbers and run the REAL
    `_allocate`. The declared outcome: the null world gets ZERO weight and the
    residual parks in the benchmark."""
    best: dict[str, tuple[str, dict]] = {}
    for cell, r in results.items():
        world = cell.split("::")[0]
        cur = best.get(world)
        if cur is None or (r["annualised_excess"] or -9) > (cur[1]["annualised_excess"] or -9):
            best[world] = (cell, r)
    sleeves = []
    for world, (cell, r) in sorted(best.items()):
        sleeves.append(_sleeve(
            f"world_{world}",
            float(r["annualised_excess"] or 0.0),
            0.10, 0.02,
            float(r["mde_annual_excess_at_t2"] or 0.0),
            f"best cell {cell}: annualised excess {r['annualised_excess']}, "
            f"verdict {r['verdict']}"))
    sleeves.append({
        "name": "benchmark_SPY", "gate": "DEPLOYABLE",
        "components": {
            "e_excess": AL.definition(0.0, "the benchmark's excess over itself"),
            "cvar": AL.definition(0.10, "synthetic market drawdown proxy"),
            "costs": AL.definition(0.0005, "one rebalance a year"),
            "uncertainty": AL.definition(0.0, "its own reference")},
        "notes": ["the parking orbit"]})
    sleeves.append({
        "name": "cash", "gate": "DEPLOYABLE",
        "components": {
            "e_excess": AL.definition(-0.07, "minus the benchmark anchor"),
            "cvar": AL.definition(0.0, "nominal cash does not draw down"),
            "costs": AL.definition(0.0, "holding cash costs nothing"),
            "uncertainty": AL.definition(0.0, "known")},
        "notes": ["thesis-gated"]})
    rows, residual, policy = AL._allocate(sleeves, "balanced", None)
    return {"personality": "balanced",
            "lambdas": AL.PERSONALITIES["balanced"],
            "rows": [{k: r[k] for k in ("sleeve", "U",
                                        "u_margin_vs_benchmark", "weight",
                                        "binding_constraint")} for r in rows],
            "residual": residual, "cash_policy": policy}


# ───────────────────────────────────────────────────────────── adjudication


#: THE DECLARED OUTCOMES. Written before the run, and the null world's row
#: depends on the CONFIG rather than on the answer — which is not a hedge but
#: the point. The full battery holds 240 OOS months and IS powered for a 3%/yr
#: effect, so the honest word for its null is NOISE and the honest end state is
#: REFUTED. The `--fast` battery holds 36 months and is NOT powered, so the
#: honest word is CANNOT DETERMINE and the honest end state is IDEA. Asserting
#: that in the fast test pins the property the vocabulary exists for: the
#: machine must NOT call an underpowered null NOISE.
DECLARED_PLANTED = {
    "linear": {"sign": +1, "state": "SUPPORTED",
               "why": "a planted linear edge, above the MDE, seen by every arm"},
    "regime": {"sign": +1, "state": "SUPPORTED",
               "why": "the pooled edge is positive because the regime recurs; "
                      "the conditionality is a separate question the era table "
                      "reports"},
    "graph": {"sign": +1, "state": "SUPPORTED",
              "why": "propagation carried only by features_graph's columns"},
}


def declared_for(cfg: Cfg) -> dict:
    """The declared end states. The `--fast` battery holds THREE YEARS of OOS
    months, and three years cannot reach any promotion bar in this machine — not
    the deflated Sharpe, not the power flag. So its declared state is IDEA
    everywhere, and asserting that is itself worth doing: a machine that
    promoted a planted edge to SUPPORTED on 36 months would be promoting on
    tape it does not have. The full battery holds 240 months and is where the
    state machine is actually exercised."""
    d = {k: dict(v) for k, v in DECLARED_PLANTED.items()}
    if cfg.fast:
        for k in d:
            d[k]["state"] = "IDEA"
            d[k]["why"] = ("36 OOS months reach no promotion bar; the fast "
                           "battery pins SIGN and family-corrected p, and pins "
                           "that the machine does NOT promote on three years")
        d["null"] = {"sign": 0, "state": "IDEA",
                     "verdict_prefix": "CANNOT DETERMINE",
                     "why": "36 OOS months cannot see a 3%/yr effect; the "
                            "machine must say so rather than say NOISE"}
    else:
        d["null"] = {"sign": 0, "state": "REFUTED",
                     "verdict_prefix": "NOISE",
                     "why": "three POWERED observations and nothing cleared "
                            "the bar"}
    return {k: v for k, v in d.items() if k in cfg.worlds}


def adjudicate(cfg: Cfg, worlds: dict, results: dict, mem: dict,
               alloc: dict) -> dict:
    declared = declared_for(cfg)
    per_world, findings = {}, []
    for world in cfg.worlds:
        cells = {k: v for k, v in results.items() if k.startswith(world + "::")}
        if not cells:
            per_world[world] = {"verdict": "NO CELLS", "pass": False}
            findings.append(f"DEFECT: world {world} produced no cells at all")
            continue
        dec = declared[world]
        best = max(cells.items(), key=lambda kv: (kv[1]["annualised_excess"] or -9))
        bk, bv = best
        planted = worlds[world]["meta"]["oracle"]["annualised_excess"]
        mde = bv["mde_annual_excess_at_t2"]
        state = mem["states"].get(world, {}).get("state")
        checks = {}
        if dec["sign"] > 0:
            checks["sign_correct"] = bool((bv["annualised_excess"] or 0) > 0)
            checks["family_corrected_p_below_0.05"] = bool(
                bv["p_holm"] is not None and bv["p_holm"] < 0.05)
            checks["bh_fdr_p_below_0.05"] = bool(bv["p_bh_fdr"] < 0.05)
            checks["planted_above_mde"] = bool(
                planted is not None and mde is not None and planted > mde)
        else:
            checks["no_cell_significant"] = all(
                (v["p_holm"] is None or v["p_holm"] >= 0.05) for v in cells.values())
            want = dec["verdict_prefix"]
            checks[f"verdict_is_{want.replace(' ', '_')}"] = all(
                str(v["verdict"]).startswith(want) for v in cells.values())
            checks["power_flag_matches_the_declaration"] = all(
                (v["powered"] is True) == (want == "NOISE")
                for v in cells.values())
        checks["evidence_state_as_declared"] = bool(state == dec["state"])
        if world == "null":
            wrow = next((r for r in alloc["rows"]
                         if r["sleeve"] == "world_null"), None)
            checks["allocator_gives_null_zero_weight"] = bool(
                wrow is not None and float(wrow["weight"]) == 0.0)
            checks["residual_parks_in_benchmark"] = bool(
                alloc["residual"]["destination"] == "benchmark_SPY")
        ok = all(checks.values())
        per_world[world] = {
            "best_cell": bk,
            "planted_effect_annualised": planted,
            "machine_mde_annual_at_t2": mde,
            "planted_over_mde": (round(planted / mde, 2)
                                 if planted and mde else None),
            "measured_annualised_excess": bv["annualised_excess"],
            "t": bv["t"], "p_raw": bv["p_raw"],
            "p_holm": bv["p_holm"], "p_bh_fdr": bv["p_bh_fdr"],
            "verdict": bv["verdict"],
            "evidence_state": state,
            "declared_state": dec["state"],
            "checks": checks,
            "PASS": ok,
        }
        if not ok:
            for name, val in checks.items():
                if not val:
                    findings.append(
                        f"MISS [{world}] {name} — planted "
                        f"{planted}/yr vs MDE {mde}/yr, measured "
                        f"{bv['annualised_excess']}/yr, verdict {bv['verdict']}, "
                        f"state {state} (declared {dec['state']})")
    for world, v in per_world.items():
        if world == "null":
            continue
        # The 2026-09-06 defect, kept as a REGRESSION CHECK rather than deleted:
        # a real planted edge that is family-significant may never read NOISE.
        # X5 gave `verdict_from` the word it was missing; if the middle of the
        # vocabulary is ever removed again, this fires again.
        if (str(v.get("verdict", "")).startswith("NOISE")
                and (v.get("p_holm") or 1.0) < 0.05):
            findings.append(
                f"FINDING [{world}]: the arm's family-corrected p is "
                f"{v['p_holm']} on a REAL planted edge and the verdict "
                f"vocabulary still returns {v['verdict']!r}. `verdict_from` has "
                "exactly two outcomes for a self-resolved arm — NOVEL (which "
                "needs the full DSR/SPA/PBO/era bar) or NOISE — so there is no "
                "word for 'significant, did not clear the deflation bar'. On "
                "short tape that reads as a false negative in the vocabulary, "
                "not in the numbers.")
        elif str(v.get("verdict", "")).startswith("SEPARATED_NOT_SURVIVING"):
            findings.append(
                f"RESOLVED [{world}] (X5, 2026-09-07): family-corrected p "
                f"{v['p_holm']} on a real planted edge now reads "
                f"{v['verdict']!r} instead of NOISE. The numbers did not move; "
                "the vocabulary gained the word between NOVEL and NOISE.")
    findings.append(
        "RESOLVED (X6, 2026-09-07): `learner/evaluate.ERAS` is still 2016-2024 "
        "BY DESIGN — a sealed receipt is sealed at its bucket names as well as "
        "its numbers — but `grade_by_era` now derives its coverage or REFUSES, "
        "and `evaluate.eras_covering(df)` picks the narrowest canonical grid "
        "that describes the frame, so no caller silently grades a 1999-2024 "
        "panel on its last nine years. This battery still derives its own eras, "
        "which is now the same answer rather than a private one.")
    return {"declared": declared, "per_world": per_world,
            "ALL_PASS": all(v.get("PASS") for v in per_world.values()),
            "findings": findings}


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:                                          # noqa: BLE001
        return None


def write_receipt(receipt: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="labor_b1_known_answer_battery")
    ap.add_argument("--fast", action="store_true",
                    help="test-sized battery (2 worlds, 1 model, 60 names)")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    cfg = Cfg(fast=a.fast)
    path = FAST_RECEIPT if a.fast else RECEIPT
    try:
        receipt = run_battery(cfg)
    except BaseException as e:                                 # noqa: BLE001
        import traceback
        write_receipt({
            "item": "LABOR_DAY_LAB_2026-09-07 / lane B / B1",
            "status": "FAILED",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            "argv": list(sys.argv), "git_commit": _git_commit(),
            "config": cfg.as_dict(),
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "note": "a traceback is a receipt",
        }, path)
        print(f"FAILED — receipt written to {path}")
        raise
    write_receipt(receipt, path)
    adj = receipt["adjudication"]
    print("\n" + "=" * 72)
    for w, v in adj["per_world"].items():
        print(f"  {w:8s} planted {v['planted_effect_annualised']!s:>8}/yr  "
              f"MDE {v['machine_mde_annual_at_t2']!s:>8}/yr  "
              f"measured {v['measured_annualised_excess']!s:>8}/yr  "
              f"p_holm {v['p_holm']!s:>10}  state {v['evidence_state']!s:16s} "
              f"{'PASS' if v['PASS'] else 'MISS'}")
    print(f"  ALL_PASS: {adj['ALL_PASS']}")
    print(f"[receipt] -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
