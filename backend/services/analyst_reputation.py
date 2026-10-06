"""Reputation-weighted analyst consensus (CHUNK C18, 2026-10-07). Offline, $0.

Replaces the `n analysts >= 5` cliff with a number that says how much the
consensus is worth: per covering firm a weight in [0.5, 1.5] from its RESOLVED
track record, and per ticker the Kish effective sample size of those weights.
Spec: `docs/research_notes/2026-10-07/analyst_reputation_spec_2026-10-07.md`.

THE THREE LEVELS (spec §1.3; K1 = pit_features.SKILL_SHRINK_K = 20, unchanged)
------------------------------------------------------------------------------
    shrunk_sh  = raw_sh * n_sh / (n_sh + K1)                       sector pool -> 0
    firm_eff   = (raw_firm * n_firm + shrunk_sh * K1) / (n_firm + K1)   firm -> ITS SECTOR
    edge_final = (raw_cell * n_cell + firm_eff * K_SUB) / (n_cell + K_SUB)  cell -> firm
    weight     = clip(1 + SKILL_SLOPE * edge_final, *SKILL_CLIP)      (unchanged map)

`raw_*` = hit rate minus the direction-conditional base rate. Every level is
computed BY CALLING `pit_features.firm_reliability` with a different grouping
key, so the resolution filter (`public_at + RESOLVE_DAYS < asof`) and the
expected-rate formula exist exactly once in the repository. `firm_reliability`
itself is not touched (ANALYST-SKILL-1's registered reproduction depends on it).
The base rate is the POOLED direction mean over every resolved claim; computing
it inside a sector would make `raw_sh` identically zero.

A brand-new firm (n_firm = n_cell = 0) gets `edge_final == shrunk_sh`: its
sector's own pooled record, not a flat 1.0. A new sector shrinks to 0 -> 1.0.

POINT IN TIME (review F2, measured -- see `pit_truth`)
-----------------------------------------------------
(1) a claim counts toward a reputation only once its 63-session outcome closed
before `asof` by the VENDOR's event_date (`firm_reliability`'s filter, `public_at`
shifted as in `crsp_pit_bridges.reliability_claims`). (2) a row is admitted only
if first seen before `asof`. Until the file carries `first_seen_utc` (the pull
writes it from its next run), "first seen" is `pulled_at` = the LAST pull: at the
current as-of the gate admits everything, and at any PAST as-of it admits only
rows the vendor stopped confirming -- adversely selected, so NOT_PIT for a
backtest. The receipt prints this.

PERSISTENCE (review F1): on its own data the weight did NOT persist out of sample
(split-half Spearman -0.31). It is computed as plumbing and labelled
`REPUTATION_WEIGHT: NOT_PERSISTENT_OOS`; it must not be presented as skill.

HONEST LIMITS (printed on the receipt)
--------------------------------------
* The horizon level is DEGENERATE: every target on disk is 12-month.
* Claims are graded on `prices_2025_26/bars.parquet` (2025-01 onward), so the
  track record is ~1.5 years of yfinance revisions, not IBES history.
* Sector = config.WHY_MOVED_TICKER_SECTOR, else the 2026-09-02 Alpaca identity
  label (mixed GICS/industry vocabulary), else "UNKNOWN" -- its own bucket.
* SKILL_CLIP (0.5, 1.5) caps the weight ratio at 3:1, so one reliable firm can
  out-vote at most three unreliable ones. Not widened here (that would be a
  parameter chosen after looking).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services import pit_features as PF

OPT = Path(_config.OPTIMUS_LEDGER_DIR)
ANALYST_DIR = OPT / "analyst"
REVISIONS_PATH = ANALYST_DIR / "target_revisions.parquet"
BARS_PATH = OPT / "prices_2025_26" / "bars.parquet"
IDENTITY_PATH = OPT / "potential_universe" / "2026-09-02.jsonl"

K1 = PF.SKILL_SHRINK_K
K_SUB = _config.ANALYST_REP_K_SUB
HORIZON = _config.ANALYST_REP_HORIZON
CLAIM_SESSIONS = _config.ANALYST_REP_CLAIM_SESSIONS
COVER_DAYS = _config.ANALYST_REP_COVER_DAYS
TARGET_MAX_AGE_DAYS = _config.ANALYST_REP_TARGET_MAX_AGE_DAYS
SCHEMA = "analyst_reputation/2"   # /2: persistence label, PIT truth, map note (review C18)
_SEP = "\x1f"

#: Same lists as scripts/contest_direction.py (copied, not imported: that module's
#: source is inside a frozen contract hash and must not gain importers that tempt edits).
BUY_GRADES = ("buy", "strong buy", "overweight", "outperform", "market outperform", "sector outperform",
              "positive", "accumulate", "add", "outperformer", "speculative buy", "top pick", "long-term buy",
              "conviction buy", "action list buy", "gradually accumulate", "above average")
HOLD_GRADES = ("neutral", "hold", "equal-weight", "market perform", "sector perform", "in-line", "peer perform",
               "perform", "sector weight", "market weight", "mixed", "fair value", "average", "sector performer",
               "hold neutral", "performer", "cautious")
SELL_GRADES = ("underweight", "underperform", "sell", "reduce", "negative", "sector underperform",
               "market underperform", "underperformer", "strong sell", "trim", "below average", "trading sell",
               "sector underweight")


class ReputationRefused(RuntimeError):
    """The reputation layer will not weight a consensus it cannot date."""


def grade_sign(g: Any) -> Optional[int]:
    s = str(g or "").strip().lower()
    if s in BUY_GRADES:
        return 1
    if s in HOLD_GRADES:
        return 0
    if s in SELL_GRADES:
        return -1
    return None


# ───────────────────────────── generic helpers ─────────────────────────────

def kish_n_effective(weights: Iterable[float]) -> Optional[float]:
    """(sum w)^2 / sum w^2: equals n only when every weight is equal; None when empty."""
    w = np.asarray([x for x in weights if x is not None and np.isfinite(x)], dtype=float)
    if w.size == 0 or float((w ** 2).sum()) <= 0:
        return None
    return float(w.sum() ** 2 / (w ** 2).sum())


def weighted_median(values: Iterable[float], weights: Iterable[float]) -> Optional[float]:
    """The first value (ascending) at which cumulative weight reaches half the total."""
    pairs = sorted((float(v), float(w)) for v, w in zip(values, weights)
                   if v is not None and w is not None and np.isfinite(v) and np.isfinite(w) and w > 0)
    if not pairs:
        return None
    tot = sum(w for _, w in pairs)
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= 0.5 * tot - 1e-12:
            return v
    return pairs[-1][0]


# ───────────────────────────── inputs ─────────────────────────────

def load_revisions(path: Path = REVISIONS_PATH) -> pd.DataFrame:
    """The dated rows plus `first_seen` (naive UTC). attrs['first_seen_basis'] says which column."""
    if not Path(path).exists():
        raise ReputationRefused(f"analyst revisions missing: {path}")
    try:
        d = pd.read_parquet(path)
    except Exception as exc:                                        # noqa: BLE001
        raise ReputationRefused(f"analyst revisions unreadable: {type(exc).__name__}: {exc}") from exc
    if "first_seen_utc" in d.columns:
        fs, basis = d["first_seen_utc"], "first_seen_utc"
        if "pulled_at" in d.columns:     # rows from before the column existed carry their pull time
            fs = fs.where(fs.notna(), d["pulled_at"])
            basis = "first_seen_utc, else pulled_at (an upper bound)"
    elif "pulled_at" in d.columns:
        fs, basis = d["pulled_at"], "pulled_at (no first_seen_utc column yet: an upper bound, excludes only)"
    else:
        raise ReputationRefused("revisions carry neither first_seen_utc nor pulled_at: undateable")
    d = d.copy()
    d["first_seen"] = pd.to_datetime(fs, utc=True, errors="coerce").dt.tz_localize(None)
    d["event_date"] = pd.to_datetime(d["event_date"], errors="coerce")
    d["ticker"] = d["ticker"].astype(str).str.upper()
    d["firm"] = d["firm"].fillna("").astype(str).str.strip()
    d = d[d["event_date"].notna() & d["first_seen"].notna() & (d["firm"] != "")]
    d.attrs["first_seen_basis"] = basis
    return d.reset_index(drop=True)


def known_before(rv: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Rows first seen AND dated strictly before `asof`. The only PIT gate on rows."""
    asof = pd.Timestamp(asof)
    return rv[(rv["first_seen"] < asof) & (rv["event_date"] < asof)]


def load_identity_sectors(path: Path = IDENTITY_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ident = r.get("identity") if isinstance(r, dict) else None
        if isinstance(ident, dict) and r.get("symbol") and ident.get("sector"):
            out[str(r["symbol"]).upper()] = str(ident["sector"])
    return out


def sector_map(tickers: Iterable[str], identity: Optional[dict] = None) -> dict[str, str]:
    """Explorer's own fallback order: config GICS map, then the Alpaca identity, else UNKNOWN."""
    identity = load_identity_sectors() if identity is None else identity
    out = {}
    for t in tickers:
        out[t] = _config.WHY_MOVED_TICKER_SECTOR.get(t) or identity.get(t) or "UNKNOWN"
    return out


def load_closes(path: Path = BARS_PATH) -> pd.DataFrame:
    """Wide close panel (sessions x symbols). Refuses without SPY (no benchmark, no outcome)."""
    if not Path(path).exists():
        raise ReputationRefused(f"bars missing: {path}")
    b = pd.read_parquet(path, columns=["symbol", "date", "close"])
    b["date"] = pd.to_datetime(b["date"])
    w = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    if "SPY" not in w.columns:
        raise ReputationRefused("bars carry no SPY: an outcome vs the market cannot be graded")
    return w


# ───────────────────────────── claims ─────────────────────────────

def build_claims(rv: pd.DataFrame, closes: pd.DataFrame, sectors: dict[str, str], *,
                 sessions: int = CLAIM_SESSIONS) -> pd.DataFrame:
    """Every dated raise/lower as a graded claim for `firm_reliability`.

    Entry = close of the first session STRICTLY after the event day; exit
    `sessions` later; outcome = 1 if sign x (stock - SPY) > 0. `public_at` is
    shifted so `public_at + RESOLVE_DAYS == res_day + 1 day` (the claim counts
    only after its exit session closed), as `crsp_pit_bridges.reliability_claims`.
    A claim whose exit is beyond the bars is not graded (absent, not a loss).
    """
    from backend.services.revision_flow import _normalise_action, _RAISE, _LOWER  # noqa: PLC0415
    act = _normalise_action(rv["target_action"])
    sign = np.where(act == _RAISE, 1, np.where(act == _LOWER, -1, 0))
    c = rv.assign(direction=sign)
    c = c[c["direction"] != 0]
    c = c[c["ticker"].isin(closes.columns)]
    cols = ["firm", "sector", "horizon", "direction", "outcome", "public_at", "ticker", "event_date", "first_seen"]
    if c.empty:
        return pd.DataFrame(columns=cols)
    dates = closes.index.values.astype("datetime64[ns]")
    day = c["event_date"].dt.normalize().values.astype("datetime64[ns]")
    i0 = np.searchsorted(dates, day, side="right")              # first session strictly after
    i1 = i0 + sessions
    # an event before the first bar has no entry session on the panel: not graded
    ok = (i0 >= 1) & (i1 < len(dates))
    c, i0, i1 = c[ok], i0[ok], i1[ok]
    col_idx = closes.columns.get_indexer(c["ticker"])
    px = closes.to_numpy(dtype=float)
    spy = closes["SPY"].to_numpy(dtype=float)
    stock = px[i1, col_idx] / px[i0, col_idx] - 1.0
    mkt = spy[i1] / spy[i0] - 1.0
    exc = stock - mkt
    good = np.isfinite(exc)
    c = c[good]
    exc, i1 = exc[good], i1[good]
    res_day = pd.to_datetime(dates[i1])
    out = pd.DataFrame({
        "firm": c["firm"].to_numpy(),
        "sector": c["ticker"].map(sectors).fillna("UNKNOWN").to_numpy(),
        "horizon": HORIZON,
        "direction": c["direction"].to_numpy(),
        "outcome": (c["direction"].to_numpy() * exc > 0).astype(float),
        "public_at": (res_day + pd.Timedelta(days=1) - pd.Timedelta(days=PF.RESOLVE_DAYS)).to_numpy(),
        "ticker": c["ticker"].to_numpy(),
        "event_date": c["event_date"].to_numpy(),
        "first_seen": c["first_seen"].to_numpy(),
    })
    return out


# ───────────────────────────── the three levels ─────────────────────────────

def reputation_tables(claims: pd.DataFrame, asof: pd.Timestamp, *, k1: float = K1,
                      k_sub: float = K_SUB) -> dict[str, pd.DataFrame]:
    """sectors / firms / cells, each from `firm_reliability` with a different key."""
    asof = pd.Timestamp(asof)
    c = claims.copy()
    c["sector"] = c["sector"].fillna("UNKNOWN").astype(str)
    c["horizon"] = c["horizon"].fillna(HORIZON).astype(str)
    c["_sh"] = c["sector"] + _SEP + c["horizon"]
    c["_cell"] = c["firm"].astype(str) + _SEP + c["_sh"]
    fr = PF.firm_reliability(c, asof, firm_col="firm")
    sr = PF.firm_reliability(c, asof, firm_col="_sh")
    cr = PF.firm_reliability(c, asof, firm_col="_cell")

    firms = pd.DataFrame({"n_firm": fr["n"].astype(int), "raw_firm": fr["edge"].astype(float)})
    firms.index.name = "firm"
    sectors = pd.DataFrame(columns=["sector", "horizon", "n_sh", "raw_sh", "shrunk_sh", "n_sh_firms"])
    cells = pd.DataFrame(columns=["firm", "sector", "horizon", "n_cell", "raw_cell"])
    if len(sr):
        sh = sr.index.to_series().str.split(_SEP, expand=True)
        sectors = pd.DataFrame({"sector": sh[0].to_numpy(), "horizon": sh[1].to_numpy(),
                                "n_sh": sr["n"].astype(int).to_numpy(), "raw_sh": sr["edge"].astype(float).to_numpy()})
        sectors["shrunk_sh"] = sectors["raw_sh"] * sectors["n_sh"] / (sectors["n_sh"] + k1)
    if len(cr):
        ck = cr.index.to_series().str.split(_SEP, expand=True)
        cells = pd.DataFrame({"firm": ck[0].to_numpy(), "sector": ck[1].to_numpy(), "horizon": ck[2].to_numpy(),
                              "n_cell": cr["n"].astype(int).to_numpy(), "raw_cell": cr["edge"].astype(float).to_numpy()})
        nf = cells.groupby(["sector", "horizon"])["firm"].nunique()
        sectors["n_sh_firms"] = [int(nf.get((s, h), 0)) for s, h in zip(sectors["sector"], sectors["horizon"])]
    tabs = {"sectors": sectors.reset_index(drop=True), "firms": firms, "cells": cells.reset_index(drop=True),
            "k1": k1, "k_sub": k_sub}
    if len(cells):
        w = [cell_weight(tabs, f, s, h) for f, s, h in zip(cells["firm"], cells["sector"], cells["horizon"])]
        for k in ("shrunk_sh", "firm_eff", "edge_final", "weight", "n_firm", "n_sh"):
            cells[k] = [x[k] for x in w]
    tabs["cells"] = cells
    return tabs


def cell_weight(tabs: dict, firm: str, sector: str, horizon: str = HORIZON) -> dict:
    """§1.3 for any (firm, sector, horizon), including ones with no history at all."""
    k1, k_sub = float(tabs["k1"]), float(tabs["k_sub"])
    sec = tabs["sectors"]
    srow = sec[(sec["sector"] == sector) & (sec["horizon"] == horizon)] if len(sec) else sec
    n_sh = int(srow["n_sh"].iloc[0]) if len(srow) else 0
    shrunk_sh = float(srow["shrunk_sh"].iloc[0]) if len(srow) else 0.0
    fr = tabs["firms"]
    n_firm = int(fr.at[firm, "n_firm"]) if firm in fr.index else 0
    raw_firm = float(fr.at[firm, "raw_firm"]) if firm in fr.index else 0.0
    firm_eff = (raw_firm * n_firm + shrunk_sh * k1) / (n_firm + k1)
    cells = tabs["cells"]
    if len(cells):
        crow = cells[(cells["firm"] == firm) & (cells["sector"] == sector) & (cells["horizon"] == horizon)]
    else:
        crow = cells
    n_cell = int(crow["n_cell"].iloc[0]) if len(crow) else 0
    raw_cell = float(crow["raw_cell"].iloc[0]) if len(crow) else 0.0
    edge = (raw_cell * n_cell + firm_eff * k_sub) / (n_cell + k_sub)
    w = float(np.clip(1.0 + PF.SKILL_SLOPE * edge, *PF.SKILL_CLIP))
    return {"firm": firm, "sector": sector, "horizon": horizon, "n_cell": n_cell, "n_firm": n_firm,
            "n_sh": n_sh, "raw_cell": raw_cell, "raw_firm": raw_firm, "shrunk_sh": shrunk_sh,
            "firm_eff": firm_eff, "edge_final": edge, "weight": w}


# ───────────────────────────── per-ticker aggregate ─────────────────────────────

def ticker_consensus(rv_known: pd.DataFrame, ticker: str, sector: str, tabs: dict,
                     asof: pd.Timestamp, *, price: Optional[float] = None,
                     cover_days: int = COVER_DAYS, target_max_age_days: int = TARGET_MAX_AGE_DAYS,
                     top: int = 5) -> Optional[dict]:
    """§1.4 over the covering firms, ALL from the revision file (one source).

    Covering firms = each firm's LATEST row on the ticker within `cover_days`
    before `asof`. Never a gate. The TARGET leg uses only latest rows at most
    `target_max_age_days` old (older -> null, `stale_target`) and is never
    computed from one firm (-> null, `single_firm`). The weighted upside is
    DIAGNOSTIC_ONLY: target-LEVEL upside is CLOSED/PERVERSE in the registry, and
    re-weighting an anti-signal does not make it a signal.
    """
    asof = pd.Timestamp(asof)
    g = rv_known[(rv_known["ticker"] == ticker)
                 & (rv_known["event_date"] >= asof - pd.Timedelta(days=cover_days))]
    if g.empty:
        return None
    last = g.sort_values("event_date").groupby("firm").tail(1)
    firms = []
    for _, r in last.iterrows():
        cw = cell_weight(tabs, r["firm"], sector)
        tgt = r.get("current_target")
        tgt = float(tgt) if tgt is not None and np.isfinite(tgt) and tgt > 0 else None
        fresh = (asof - pd.Timestamp(r["event_date"])).days <= target_max_age_days
        firms.append({"firm": r["firm"], "weight": round(cw["weight"], 4), "stance": grade_sign(r.get("to_grade")),
                      "to_grade": r.get("to_grade"), "target": tgt, "target_fresh": bool(fresh),
                      "n_cell": cw["n_cell"], "n_firm": cw["n_firm"],
                      "edge_final": round(cw["edge_final"], 5), "last_action_utc": str(r["event_date"])[:19]})
    w_all = [f["weight"] for f in firms]
    st = [(f["weight"], f["stance"]) for f in firms if f["stance"] is not None]
    tg = [(f["weight"], f["target"]) for f in firms if f["target"] is not None and f["target_fresh"]]
    n_any_target = sum(1 for f in firms if f["target"] is not None)
    miss: dict[str, str] = {}
    ws = (sum(w * s for w, s in st) / sum(w for w, _ in st)) if st else None
    wmed, disp = None, None
    if len(tg) >= 2:
        wmed = weighted_median([x for _, x in tg], [w for w, _ in tg])
        sw = sum(w for w, _ in tg)
        mu = sum(w * x for w, x in tg) / sw
        disp = math.sqrt(sum(w * (x - mu) ** 2 for w, x in tg) / sw) / mu if mu > 0 else None
    elif len(tg) == 1:
        miss["weighted_median_target"] = "single_firm: one fresh target is that firm's target, not a consensus"
    elif n_any_target:
        miss["weighted_median_target"] = (f"stale_target: no covering firm's target is <= {target_max_age_days} "
                                          "days old")
    else:
        miss["weighted_median_target"] = "no covering firm carries a numeric target"
    bearing = sorted(firms, key=lambda f: -abs(f["weight"] * (f["stance"] if f["stance"] is not None else 0)))
    return {
        "label": PERSISTENCE_LABEL_UNKNOWN,
        "source": "analyst/target_revisions.parquet (one source for every number here)",
        "n_covering_firms": len(firms),
        "sum_of_weights": round(float(sum(w_all)), 4),
        "mean_weight": round(float(np.mean(w_all)), 4),
        "n_effective_kish": round(kish_n_effective(w_all), 3) if w_all else None,
        "n_with_stance": len(st), "n_fresh_targets": len(tg),
        "weighted_stance": round(ws, 4) if ws is not None else None,
        "flat_stance": round(sum(s for _, s in st) / len(st), 4) if st else None,
        "weighted_median_target": wmed,
        "weighted_upside_DIAGNOSTIC_ONLY": (round(wmed / price - 1.0, 4) if (wmed and price) else None),
        "diagnostic_note": "target-LEVEL upside is CLOSED/PERVERSE (t -3.6 large/mid, -7.2 small); never displayed",
        "dispersion": round(disp, 4) if disp is not None else None,
        "weight_bearing_firms": bearing[:top],
        "missing_because": miss,
        "sector": sector,
    }


# ───────────────────────────── out-of-sample persistence (review F1) ─────────────

PERSISTENCE_LABEL_UNKNOWN = "REPUTATION_WEIGHT: PERSISTENCE_UNTESTED"


def _spearman(a: pd.Series, b: pd.Series) -> Optional[float]:
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(j) < 3:
        return None
    return float(j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank()))


def _clustered_edges(c: pd.DataFrame, *, demean: bool) -> pd.DataFrame:
    """Per firm: edge over (firm, ticker, month, direction) CLUSTERS -- several raises of
    one name in one month share one outcome, so they count once. Base rate pooled by
    direction (as the module does) or matched on (event month, direction)."""
    c = c.copy()
    c["month"] = pd.to_datetime(c["event_date"]).dt.to_period("M").astype(str)
    if demean:
        c["expected"] = c.groupby(["month", "direction"])["outcome"].transform("mean")
    else:
        c["expected"] = c.groupby("direction")["outcome"].transform("mean")
    c["resid"] = c["outcome"] - c["expected"]
    cl = c.groupby(["firm", "ticker", "month", "direction"])["resid"].mean().reset_index()
    g = cl.groupby("firm")["resid"]
    return pd.DataFrame({"n_clusters": g.size(), "edge": g.mean()})


def persistence_test(claims: pd.DataFrame, *, thresholds: tuple[int, ...] = (20, 50, 100),
                     n_boot: int = 500, seed: int = _config.ANALYST_REP_PERSIST_SEED) -> dict:
    """Split at the MEDIAN event date; do the first half's firm edges rank the second's?

    Printed: (a) raw firm edge with the pooled base and (b) with a month x direction
    base, per min-clusters threshold; (c) the MODULE's own weight
    (`reputation_tables` on the first half only; firm = claims-weighted mean cell
    weight) vs the second half's month x direction edge at the middle threshold.
    Verdict on (c): PERSISTENT_OOS only if Spearman > 0 AND the firm-bootstrap 95%
    CI excludes zero; else NOT_PERSISTENT_OOS.
    """
    c = claims.dropna(subset=["event_date", "outcome"]).copy()
    if len(c) < 100 or c["firm"].nunique() < 5:
        raise ReputationRefused(f"persistence test needs >= 100 claims from >= 5 firms (got {len(c)} claims, "
                                f"{c['firm'].nunique()} firms): refusing rather than reporting a correlation of nothing")
    ed = pd.to_datetime(c["event_date"])
    split = ed.median()
    a, b = c[ed < split], c[ed >= split]
    rows = []
    for thr in thresholds:
        out: dict[str, Any] = {"min_clusters_per_half": thr}
        for name, dm in (("pooled_base", False), ("month_x_direction", True)):
            ea, eb = _clustered_edges(a, demean=dm), _clustered_edges(b, demean=dm)
            keep = ea.index[ea["n_clusters"] >= thr].intersection(eb.index[eb["n_clusters"] >= thr])
            out[f"n_firms_{name}"] = int(len(keep))
            r = _spearman(ea.loc[keep, "edge"], eb.loc[keep, "edge"]) if len(keep) >= 3 else None
            out[f"spearman_{name}"] = round(r, 4) if r is not None else None
        rows.append(out)
    mid = thresholds[len(thresholds) // 2]
    far = ed.max() + pd.Timedelta(days=PF.RESOLVE_DAYS + 400)
    cells = reputation_tables(a, far)["cells"]          # first half only; every first-half claim counts
    fw = cells.assign(_wn=cells["weight"] * cells["n_cell"]).groupby("firm")[["_wn", "n_cell"]].sum()
    w_a = fw["_wn"] / fw["n_cell"]
    eb = _clustered_edges(b, demean=True)
    eb_pool = _clustered_edges(b, demean=False)
    keep = w_a.index.intersection(eb.index[eb["n_clusters"] >= mid])
    rho = _spearman(w_a.loc[keep], eb.loc[keep, "edge"])
    rho_pool = _spearman(w_a.loc[keep], eb_pool.loc[keep, "edge"])
    rng = np.random.default_rng(seed)
    boots = []
    ks = np.asarray(keep)
    if len(ks) >= 3:
        for _ in range(n_boot):
            pick = rng.choice(ks, size=len(ks), replace=True)
            x, y = w_a.loc[pick].to_numpy(), eb.loc[pick, "edge"].to_numpy()
            if np.unique(x).size > 2 and np.unique(y).size > 2:
                boots.append(float(pd.Series(x).rank().corr(pd.Series(y).rank())))
    lo, hi = (np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan))
    persistent = rho is not None and rho > 0 and bool(np.isfinite(lo)) and lo > 0
    verdict = "PERSISTENT_OOS" if persistent else "NOT_PERSISTENT_OOS"
    return {
        "schema": "analyst_reputation_persistence/1",
        "split_at_median_event_date": str(split.date()),
        "n_claims": int(len(c)), "n_claims_first_half": int(len(a)), "n_claims_second_half": int(len(b)),
        "clusters": "(firm, ticker, event month, direction): one outcome per cluster",
        "by_threshold": rows,
        "module_weight_vs_second_half": {
            "min_clusters_second_half": mid, "n_firms": int(len(keep)),
            "spearman_vs_month_x_direction_edge": round(rho, 4) if rho is not None else None,
            "spearman_vs_pooled_edge": round(rho_pool, 4) if rho_pool is not None else None,
            "firm_bootstrap_ci95": [round(float(lo), 4), round(float(hi), 4)], "n_boot": n_boot, "seed": seed},
        "verdict": verdict,
        # headline rho = vs the POOLED-base edge (the module's own edge definition); the
        # month x direction read is printed beside it
        "label": (f"REPUTATION_WEIGHT: {verdict} (rho {rho_pool:+.2f}; {rho:+.2f} month x direction)"
                  if rho is not None and rho_pool is not None else f"REPUTATION_WEIGHT: {verdict}"),
        "meaning": ("the weight is computed (plumbing) and must NOT be presented as skill" if not persistent
                    else "first-half weights rank second-half edges with a CI excluding zero"),
    }


# ───────────────────────────── the monthly receipt ─────────────────────────────

def receipt_path(month: str, run_id: str, base: Optional[Path] = None) -> Path:
    """Run id in the name (review F11): a second run can never take an earlier receipt's slot."""
    return (base or ANALYST_DIR) / f"reputation_weights_{month}_{run_id}.json"


def current_month_receipt(month: str, base: Optional[Path] = None) -> Optional[Path]:
    """The newest receipt of the month written under the CURRENT schema; older-schema
    receipts (e.g. the 2026-10 /1 file) stay on disk untouched and are not read back."""
    for q in sorted((base or ANALYST_DIR).glob(f"reputation_weights_{month}*.json"), reverse=True):
        try:
            if json.loads(q.read_text(encoding="utf-8")).get("schema") == SCHEMA:
                return q
        except ValueError:
            continue
    return None


def pit_truth(rv: pd.DataFrame) -> dict:
    """Review F2: what the first-seen gate actually does on this file, measured."""
    has_col = "first_seen_utc" in rv.columns and rv["first_seen_utc"].notna().any()
    out: dict[str, Any] = {"first_seen_column": "first_seen_utc" if has_col else None}
    if "pulled_at" in rv.columns:
        pulled = pd.to_datetime(rv["pulled_at"], utc=True, errors="coerce")
        if pulled.notna().any():
            day = pulled.dt.date
            mode = day.mode().iloc[0]
            out["pulled_at_mode_day"] = str(mode)
            out["share_rows_pulled_at_mode_day"] = round(float((day == mode).mean()), 4)
    if not has_col:
        out["status"] = "NOT_PIT"
        out["statement"] = ("No first_seen_utc on this file: rows carry pulled_at = the LAST pull. PIT rests on the "
                            "vendor's event_date alone. At any PAST as-of the first-seen filter admits only rows the "
                            "vendor stopped confirming (adversely selected); at the current as-of it admits everything. "
                            "scripts/pull_analyst_targets.py writes first_seen_utc (MIN semantics) from its next run.")
    else:
        out["status"] = "FIRST_SEEN_FROM_PULL"
        out["statement"] = ("first_seen_utc present; rows that predate the column carry their last pulled_at "
                            "(an upper bound). A past as-of before the column's first pull is still adversely selected.")
    return out


def compute_receipt(asof: pd.Timestamp, *, rv: Optional[pd.DataFrame] = None,
                    closes: Optional[pd.DataFrame] = None, identity: Optional[dict] = None,
                    persistence: Optional[dict] = None) -> dict:
    # NOT normalised to midnight: rows dated by pulled_at (the LAST pull, an upper
    # bound) from a pull earlier the same day would all be excluded.
    asof = pd.Timestamp(asof).floor("min")
    rv = load_revisions() if rv is None else rv
    closes = load_closes() if closes is None else closes
    known = known_before(rv, asof)
    sectors = sector_map(sorted(set(known["ticker"])), identity)
    claims = build_claims(known, closes, sectors)
    tabs = reputation_tables(claims, asof)
    if persistence is None:
        try:
            persistence = persistence_test(claims)
        except ReputationRefused as exc:
            persistence = {"verdict": "REFUSED", "why": str(exc), "label": "REPUTATION_WEIGHT: PERSISTENCE_REFUSED"}
    cells = tabs["cells"]
    firms = tabs["firms"].reset_index()
    if len(cells):
        fw = (cells.assign(_wn=cells["weight"] * cells["n_cell"]).groupby("firm")
              .agg(n=("n_cell", "sum"), wn=("_wn", "sum"), n_sectors=("sector", "nunique")))
        fw["weight_mean"] = fw["wn"] / fw["n"]
        firms = firms.merge(fw[["weight_mean", "n_sectors"]].reset_index(), on="firm", how="left")
    resolved = int(firms["n_firm"].sum()) if len(firms) else 0
    lo, hi = PF.SKILL_CLIP
    clip_lo = round(float((cells["weight"] <= lo + 1e-9).mean()), 4) if len(cells) else None
    clip_hi = round(float((cells["weight"] >= hi - 1e-9).mean()), 4) if len(cells) else None
    return {
        "schema": SCHEMA, "asof": asof.isoformat(), "month": asof.strftime("%Y-%m"),
        "builder": "backend/services/analyst_reputation.py compute_receipt",
        "label": persistence.get("label"),
        "persistence": persistence,
        "constants": {"k1": K1, "k1_source": "pit_features.SKILL_SHRINK_K (unchanged)", "k_sub": K_SUB,
                      "skill_slope": PF.SKILL_SLOPE, "skill_clip": list(PF.SKILL_CLIP),
                      "resolve_days": PF.RESOLVE_DAYS, "claim_sessions": CLAIM_SESSIONS,
                      "cover_days": COVER_DAYS, "target_max_age_days": TARGET_MAX_AGE_DAYS, "horizon": HORIZON},
        "map_note": {"statement": ("SKILL_SLOPE 10 and SKILL_CLIP (0.5, 1.5) were frozen 2026-09-26 in pit_features for "
                                   "an edge shrunk toward ZERO; here they map an edge shrunk toward the firm and the "
                                   "firm toward its sector, so more mass reaches the clip. Not re-tuned. Saturation "
                                   "(|edge| 0.05) is below one SE of a 40-claim hit rate."),
                     "share_cells_at_lower_clip": clip_lo, "share_cells_at_upper_clip": clip_hi,
                     "review_measured": ("37.6% of the weights DISPLAYED as weight-bearing firms on the "
                                         "2026-10-06T214339Z Explorer receipt sat at a clip")},
        "pit": {"rows_first_seen_basis": rv.attrs.get("first_seen_basis"),
                "rows_total": int(len(rv)), "rows_known_before_asof": int(len(known)),
                "claims_built": int(len(claims)), "claims_resolved_before_asof": resolved,
                "claim_rule": "dated raise/lower; outcome = sign x (stock - SPY) > 0 over "
                              f"{CLAIM_SESSIONS} sessions from the first close strictly after the event day; "
                              "counts only once its exit session closed before asof (by the vendor's event_date)",
                **pit_truth(rv)},
        "limits": ["horizon level DEGENERATE: every target on disk is 12-month",
                   "claims graded on prices_2025_26/bars.parquet only (2025-01 onward)",
                   "sector vocabulary mixes config GICS (12 tickers) and Alpaca industry labels; UNKNOWN is its own bucket",
                   "SKILL_CLIP (0.5, 1.5) caps one firm's weight at 3x another's",
                   "claims sharing a ticker-month share an outcome: the n behind K1/K_SUB is overstated"],
        "sectors": tabs["sectors"].round(6).to_dict(orient="records"),
        "firms": firms.round(6).to_dict(orient="records"),
        "cells": cells.round(6).to_dict(orient="records"),
    }


def tables_from_receipt(blob: dict) -> dict:
    sectors = pd.DataFrame(blob.get("sectors") or [],
                           columns=["sector", "horizon", "n_sh", "raw_sh", "shrunk_sh", "n_sh_firms"])
    firms = pd.DataFrame(blob.get("firms") or [], columns=["firm", "n_firm", "raw_firm"]).set_index("firm")
    cells = pd.DataFrame(blob.get("cells") or [], columns=["firm", "sector", "horizon", "n_cell", "raw_cell"])
    c = blob.get("constants") or {}
    return {"sectors": sectors, "firms": firms, "cells": cells,
            "k1": c.get("k1", K1), "k_sub": c.get("k_sub", K_SUB)}


def _write_new(p: Path, blob: dict) -> None:
    if p.exists():
        raise ReputationRefused(f"refusing to overwrite receipt {p.name}")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(blob, ensure_ascii=False, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(p)


def monthly_receipt(asof: pd.Timestamp, *, base: Optional[Path] = None, write: bool = True,
                    **kw: Any) -> tuple[dict, Optional[Path], bool]:
    """(blob, path, written_now). The month's FIRST run writes the weights receipt and
    its persistence receipt; later runs read it back and never overwrite. With
    `write=False` (a dry run) NOTHING is written: the blob is computed in memory
    and the path is None unless the month's receipt already exists."""
    asof = pd.Timestamp(asof)
    have = current_month_receipt(asof.strftime("%Y-%m"), base)
    if have is not None:
        return json.loads(have.read_text(encoding="utf-8")), have, False
    blob = compute_receipt(asof, **kw)
    if not write:
        return blob, None, False
    run_id = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    p = receipt_path(asof.strftime("%Y-%m"), run_id, base)
    per = blob.get("persistence") or {}
    if per.get("verdict") in ("PERSISTENT_OOS", "NOT_PERSISTENT_OOS"):
        pp = (base or ANALYST_DIR) / f"reputation_persistence_{run_id}.json"
        _write_new(pp, {**per, "asof": blob["asof"], "weights_receipt": p.name})
        blob["persistence"] = {**per, "receipt": pp.name}
    _write_new(p, blob)
    return blob, p, True
