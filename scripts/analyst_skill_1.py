"""ANALYST-SKILL-1, run AS REGISTERED -- does broker identity add ranking information
over the equal-weighted target consensus?

    python -m scripts.analyst_skill_1 --run

Prereg: `C:/Users/mrthn/Aegis module/TRIALS/PREREG_ANALYST_SKILL_1.md`, registered
2026-08-31, never run before this script (handoff 2026-09-25 chunk C1).
Instrument: `tr_ibes.ptgdetu` from the WRDS bulk parquet on disk
(`backend/data/optimus/wrds/bulk/tr_ibes__ptgdetu.parquet`), CRSP daily
(`crsp_dsf_<year>.parquet`), delistings from `crsp__dsedelist`.

THE DECISION RULE, COPIED VERBATIM FROM THE PREREG (§2-§4, §6)
==============================================================
§2 Primary metric -- the ONE deciding number:
  **ΔIC** = mean over evaluation months of
  (Spearman rank-IC of skill-weighted upside vs fwd 1m return) -
  (Spearman rank-IC of equal-weighted upside vs fwd 1m return),
  paired by month, on an identical name-month panel.
  t-statistic: paired across evaluation months (Newey-West lag 3).

§3 Decision rule:
  - **Adopt**: ΔIC > 0 with paired t >= 2.0 over all evaluation months.
  - **Reject**: t < 2.0. This closes THIS weighting scheme, not the existence of
    analyst information -- `FAILED_VARIANT`, not `MECHANISM_REJECTED`.
  - **Minimum window:** the full evaluation span; exactly one evaluation event.
  - **Contamination clause:** any target whose name shows a `cfacpr` change
    between `anndats` and the evaluation month is excluded from BOTH arms.

§4 Frozen parameters:
  estimation window   targets with anndats 2013-01-01 .. 2018-12-31
  evaluation window   monthly cross-sections 2019-01 .. 2024-12
  target horizon      horizon = 12 months only
  staleness           a broker's target is active for 180 days from anndats
  broker skill        -(median absolute error of implied vs realised 12m log gross
                      return), per estimid, estimation-window targets only
  shrinkage           toward the grand median: w = n/(n+20)
  weighting           weight = shrunk-skill percentile + 0.5
  deciding level      broker (estimid); analyst (amaskcd) descriptive only
  entry               first close >= 3 calendar days after the month cut
  realised return     CRSP total-return index, delist-inclusive
  minimum arms        >= 2 distinct brokers with active targets per name-month

§6 Power: declared effect ΔIC = +0.010. "The realised sd(ΔIC) is computed and
  compared to the assumption FIRST; if the realised MDE exceeds the declared
  effect size, the verdict is recorded as POWER-LIMITED ... never as a null."
  Here: MDE = 2 x the NW(3) standard error of the mean ΔIC (the deciding t's own
  SE; the naive 2*sd/sqrt(n) is printed beside it). POWER_FAILED prints NO arm
  number (ANALYST-IDENT-1 precedent).

IMPLEMENTATION CHOICES THE PREREG DID NOT FIX (named, made once, before the run)
===============================================================================
* month cut = the last calendar day of the month before the evaluation month;
  active = anndats in (cut - 180d, cut]; a broker's LATEST active target per name.
* upside = target / last close <= cut - 1, both UNADJUSTED (ptgdetu is unadjusted).
* fwd 1m return: entry = first close >= cut + 3d; exit = first close >= entry
  date + 1 calendar month; compounded from CRSP `ret`, times (1 + dlret) when the
  name delists inside the window (Shumway fill via `tracker_ibes_backtest`).
* implied (estimation) = log(target / last close <= anndats, within 7d);
  realised = log total return from that close to the last close <= anndats+365d
  (within 15d, or the delisting).
* "grand median" = -median |error| pooled over every estimation-window target.
  A broker with no estimation-window target is at n=0 and so AT the grand median.
* IBES ticker -> permno: `ibcrsphist`, lowest `score` link valid at anndats.
* December 2024's forward month needs January 2025 CRSP, which is not on disk:
  that month is recorded as MISSING (71 of 72 months), not filled.
* small / large-mid split (report only): CRSP market cap at the cut < $2B.

KNOWN DESIGN LEAK (named, not fixed -- the rule does not move)
=============================================================
The frozen estimation window ends 2018-12-31 but its 12-month outcomes run to
2019-12-31, overlapping the first twelve evaluation months. The registered run
is executed exactly; a REPORT-ONLY sensitivity estimates skill from targets with
anndats <= 2017-12-31 (every outcome resolved before 2019) and is printed beside
it. It does not decide.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
BULK = WRDS / "bulk"
OUT_DIR = REPO / "backend" / "data" / "optimus" / "analyst"
PREREG = Path("C:/Users/mrthn/Aegis module/TRIALS/PREREG_ANALYST_SKILL_1.md")

# ── §4, frozen ───────────────────────────────────────────────────────────────
EST_START, EST_END = "2013-01-01", "2018-12-31"
EVAL_START, EVAL_END = "2019-01", "2024-12"
HORIZON = 12
STALE_DAYS = 180
SHRINK_K = 20
WEIGHT_OFFSET = 0.5
ENTRY_LAG_DAYS = 3
MIN_BROKERS = 2
DECLARED_EFFECT = 0.010
T_ADOPT = 2.0
NW_LAGS = 3
# ── implementation conventions (docstring) ──────────────────────────────────
PRICE_TOL_DAYS = 7
REALISED_TOL_DAYS = 15
SMALL_CAP_USD = 2e9
MIN_NAMES_PER_MONTH = 10
SENSITIVITY_EST_END = "2017-12-31"

VERDICTS = ("ADOPT", "REJECT", "POWER_FAILED")


# ═══════════════════════════ statistics (pure) ══════════════════════════════

def nw_se(x: np.ndarray, lags: int = NW_LAGS) -> float:
    """Newey-West (Bartlett) standard error of the mean of x."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lags + 1.0)) * float(e[L:] @ e[:-L]) / n
    return float(np.sqrt(max(s, 0.0) / n))


def broker_skill(grades: pd.DataFrame, level: str = "estimid") -> tuple[pd.DataFrame, float, float]:
    """Per-`level` skill -> shrunk skill -> percentile -> weight (§4).

    `grades` needs `level`, `implied_log`, `realized_log`. Returns (table,
    grand_median_skill, prior_weight) where prior_weight is what a broker with
    no estimation-window target receives (n=0 -> exactly the grand median).
    """
    g = grades.dropna(subset=[level, "implied_log", "realized_log"])
    ae = (g["implied_log"] - g["realized_log"]).abs()
    grand = -float(ae.median())
    t = pd.DataFrame({"n": ae.groupby(g[level]).size(),
                      "skill": -ae.groupby(g[level]).median()})
    w = t["n"] / (t["n"] + SHRINK_K)
    t["shrunk"] = w * t["skill"] + (1.0 - w) * grand
    t["pct"] = t["shrunk"].rank(pct=True)
    t["weight"] = t["pct"] + WEIGHT_OFFSET
    s = np.sort(t["shrunk"].to_numpy())
    # the grand median's percentile among the measured brokers (mean-rank ties)
    lo, hi = np.searchsorted(s, grand, "left"), np.searchsorted(s, grand, "right")
    prior_pct = ((lo + hi + 1) / 2.0) / len(s) if len(s) else 0.5
    return t, grand, float(prior_pct + WEIGHT_OFFSET)


def monthly_ic(panel: pd.DataFrame, weights: pd.Series, prior: float,
               level: str = "estimid") -> pd.DataFrame:
    """Per month: Spearman IC of EW and skill-weighted consensus upside vs fwd.

    `panel`: month, permno, `level`, upside, fwd_ret (+ optional mcap). Names
    with < MIN_BROKERS distinct `level` values leave BOTH arms.
    """
    p = panel.dropna(subset=["upside", "fwd_ret"]).copy()
    p["w"] = p[level].map(weights).astype(float).fillna(prior)
    k = p.groupby(["month", "permno"])[level].transform("nunique")
    p = p[k >= MIN_BROKERS]
    p["wu"] = p["w"] * p["upside"]
    agg = p.groupby(["month", "permno"]).agg(ew=("upside", "mean"), wu=("wu", "sum"),
                                             ws=("w", "sum"), fwd=("fwd_ret", "first"))
    if "mcap" in p.columns:
        agg["mcap"] = p.groupby(["month", "permno"])["mcap"].first()
    agg["sw"] = agg["wu"] / agg["ws"]
    rows = []
    for m, g in agg.groupby(level=0):
        if len(g) < MIN_NAMES_PER_MONTH:
            continue
        rf = g["fwd"].rank()
        rows.append({"month": m, "n_names": len(g),
                     "ic_ew": float(g["ew"].rank().corr(rf)),
                     "ic_sw": float(g["sw"].rank().corr(rf))})
    out = pd.DataFrame(rows)
    if len(out):
        out["dic"] = out["ic_sw"] - out["ic_ew"]
    return out


def split_ic(panel: pd.DataFrame, weights: pd.Series, prior: float, level: str = "estimid") -> dict:
    """Report-only: ΔIC within small (< $2B) and large/mid names."""
    out = {}
    if "mcap" not in panel.columns:
        return out
    for name, mask in (("small", panel["mcap"] < SMALL_CAP_USD),
                       ("largemid", panel["mcap"] >= SMALL_CAP_USD)):
        ic = monthly_ic(panel[mask], weights, prior, level)
        if len(ic):
            out[name] = {"months": int(len(ic)), "mean_dic": round(float(ic["dic"].mean()), 5),
                         "t_nw3": round(float(ic["dic"].mean() / nw_se(ic["dic"].values)), 3),
                         "mean_names": round(float(ic["n_names"].mean()), 1)}
    return out


def decide(ic: pd.DataFrame) -> dict:
    """The POWER gate first, then (only if it passes) the registered rule."""
    d = ic["dic"].to_numpy(dtype=float)
    n = int(np.isfinite(d).sum())
    sd = float(np.nanstd(d, ddof=1)) if n > 1 else float("nan")
    se = nw_se(d)
    gate = {"n_months": n, "realised_sd_dic": round(sd, 5), "assumed_sd_dic": 0.020,
            "nw3_se": round(se, 6), "mde_nw3": round(2.0 * se, 5),
            "mde_naive": round(2.0 * sd / np.sqrt(n), 5) if n else None,
            "declared_effect": DECLARED_EFFECT}
    if not np.isfinite(se) or 2.0 * se > DECLARED_EFFECT:
        return {"verdict": "POWER_FAILED", "power_gate": {**gate, "passed": False},
                "note": "realised MDE exceeds the declared effect: a design failure, "
                        "not a null about brokers; no arm number is printed"}
    mean = float(np.nanmean(d))
    t = mean / se
    verdict = "ADOPT" if (mean > 0 and t >= T_ADOPT) else "REJECT"
    return {"verdict": verdict, "power_gate": {**gate, "passed": True},
            "delta_ic_mean": round(mean, 6), "t_nw3": round(t, 3),
            "mean_ic_ew": round(float(ic["ic_ew"].mean()), 5),
            "mean_ic_sw": round(float(ic["ic_sw"].mean()), 5)}


def by_year(ic: pd.DataFrame) -> dict:
    y = pd.PeriodIndex(ic["month"], freq="M").year
    g = ic.groupby(y)
    return {int(k): {"months": int(len(v)), "mean_dic": round(float(v["dic"].mean()), 5),
                     "mean_ic_ew": round(float(v["ic_ew"].mean()), 5),
                     "mean_ic_sw": round(float(v["ic_sw"].mean()), 5),
                     "share_months_dic_pos": round(float((v["dic"] > 0).mean()), 3)}
            for k, v in g}


def attenuation_diagnostic(ic: pd.DataFrame, lags: int = NW_LAGS) -> dict:
    """REPORT-ONLY: is ΔIC information, or skill-weighting shrinking whatever IC
    the consensus has? Regress monthly ΔIC on the EW IC (NW-HAC). A slope < 0
    with an intercept ~ 0 means the weighting DAMPS the consensus: it helps when
    the consensus is an anti-signal and hurts when it works. The intercept is
    the ΔIC in a month where the consensus itself carries nothing."""
    d = ic.dropna(subset=["dic", "ic_ew"])
    n = len(d)
    X = np.c_[np.ones(n), d["ic_ew"].to_numpy()]
    y = d["dic"].to_numpy()
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    inv = np.linalg.inv(X.T @ X)
    u = X * e[:, None]
    S = u.T @ u / n
    for L in range(1, lags + 1):
        G = u[L:].T @ u[:-L] / n
        S += (1.0 - L / (lags + 1.0)) * (G + G.T)
    V = n * inv @ S @ inv
    pos, neg = d[d["ic_ew"] > 0], d[d["ic_ew"] <= 0]
    return {"corr_dic_ic_ew": round(float(d["dic"].corr(d["ic_ew"])), 4),
            "slope": round(float(b[1]), 5), "slope_t_nw3": round(float(b[1] / np.sqrt(V[1, 1])), 2),
            "intercept_dic_at_zero_ic": round(float(b[0]), 6),
            "intercept_t_nw3": round(float(b[0] / np.sqrt(V[0, 0])), 3),
            "months_ic_ew_pos": {"n": int(len(pos)), "mean_dic": round(float(pos["dic"].mean()), 5)},
            "months_ic_ew_nonpos": {"n": int(len(neg)), "mean_dic": round(float(neg["dic"].mean()), 5)},
            "share_abs_ic_sw_below_abs_ic_ew": round(float((d["ic_sw"].abs() < d["ic_ew"].abs()).mean()), 3)}


def evaluate(panel: pd.DataFrame, weights: pd.Series, prior: float, *,
             level: str = "estimid") -> dict:
    """Core: ΔIC series -> power gate -> (by-year, split, then t and verdict)."""
    ic = monthly_ic(panel, weights, prior, level)
    if ic.empty:
        return {"verdict": "POWER_FAILED", "note": "no evaluable month", "n_months": 0}
    res = decide(ic)
    if res["verdict"] != "POWER_FAILED":
        # by-year and the size split BEFORE the t is read (protocol 11)
        res = {"by_year": by_year(ic), "size_split": split_ic(panel, weights, prior, level),
               **res}
        yrs = sorted(res["by_year"])
        res["leave_one_year_out"] = {
            int(y): round(float(ic.loc[pd.PeriodIndex(ic["month"], freq="M").year != y, "dic"].mean()), 5)
            for y in yrs}
    res["monthly"] = ic
    return res


# ═══════════════════════════ data (the real run) ════════════════════════════

def load_targets(start: str, end: str) -> pd.DataFrame:
    t = pd.read_parquet(BULK / "tr_ibes__ptgdetu.parquet",
                        columns=["ticker", "estimid", "amaskcd", "horizon", "value",
                                 "estcur", "usfirm", "anndats"],
                        filters=[("usfirm", "==", 1), ("horizon", "==", str(HORIZON))])
    t = t[(t["estcur"] == "USD") & t["value"].notna() & (t["value"] > 0)]
    t["anndats"] = pd.to_datetime(t["anndats"])
    t = t[(t["anndats"] >= start) & (t["anndats"] <= end)].drop(columns=["usfirm", "estcur", "horizon"])
    link = pd.read_parquet(BULK / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet")
    for c in ("sdate", "edate"):
        link[c] = pd.to_datetime(link[c])
    m = t.reset_index(drop=True).reset_index().merge(
        link[["ticker", "permno", "sdate", "edate", "score"]], on="ticker", how="inner")
    m = m[(m["anndats"] >= m["sdate"]) & (m["anndats"] <= m["edate"]) & m["permno"].notna()]
    m = m.sort_values(["index", "score"]).drop_duplicates("index", keep="first")
    m["permno"] = m["permno"].astype("int64")
    return m.drop(columns=["index", "sdate", "edate", "score"]).reset_index(drop=True)


def load_prices(first_year: int, last_year: int) -> pd.DataFrame:
    frames = []
    for y in range(first_year, last_year + 1):
        f = WRDS / f"crsp_dsf_{y}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f, columns=["permno", "date", "prc", "ret", "cfacpr", "shrout"]))
    if not frames:
        raise SystemExit("REFUSED: no CRSP daily files on disk")
    px = pd.concat(frames, ignore_index=True)
    del frames
    px["date"] = pd.to_datetime(px["date"])
    px["prc"] = px["prc"].abs()
    px = px[px["prc"] > 0]
    px["ret"] = pd.to_numeric(px["ret"], errors="coerce")
    px = px.sort_values(["permno", "date"]).reset_index(drop=True)
    px["tri"] = (1.0 + px["ret"].fillna(0.0)).groupby(px["permno"]).cumprod()
    px["cfacpr"] = px["cfacpr"].where(px["cfacpr"].notna() & (px["cfacpr"] != 0), 1.0)
    return px


def load_delist() -> pd.DataFrame:
    sys.path.insert(0, str(REPO))
    from scripts.tracker_ibes_backtest import load_delistings
    d = load_delistings()
    return d[["permno", "dlstdt", "dlret_used"]].dropna(subset=["dlstdt"])


def _asof(left: pd.DataFrame, px: pd.DataFrame, on: str, cols: list[str], tol: int | None,
          direction: str = "backward", suffix: str = "") -> pd.DataFrame:
    r = px[["permno", "date", *cols]].rename(columns={c: c + suffix for c in cols})
    r = r.rename(columns={"date": "pxdate" + suffix}).sort_values("pxdate" + suffix)
    kw = {"tolerance": pd.Timedelta(days=tol)} if tol is not None else {}
    return pd.merge_asof(left.sort_values(on), r, left_on=on, right_on="pxdate" + suffix,
                         by="permno", direction=direction, **kw)


def grade_targets(t: pd.DataFrame, px: pd.DataFrame, dl: pd.DataFrame) -> pd.DataFrame:
    """implied_log / realized_log for each estimation-window target."""
    g = _asof(t, px, "anndats", ["prc", "tri"], PRICE_TOL_DAYS, suffix="0")
    g = g[g["prc0"].notna()]
    g["tdate"] = g["anndats"] + pd.Timedelta(days=365)
    g = _asof(g, px, "tdate", ["tri"], None, suffix="1")
    g = g.merge(dl, on="permno", how="left")
    died = g["dlstdt"].notna() & (g["dlstdt"] > g["anndats"]) & (g["dlstdt"] <= g["tdate"])
    fresh = (g["tdate"] - g["pxdate1"]).dt.days <= REALISED_TOL_DAYS
    g = g[(fresh | died) & g["tri1"].notna()].copy()
    died = g["dlstdt"].notna() & (g["dlstdt"] > g["anndats"]) & (g["dlstdt"] <= g["tdate"])
    factor = np.where(died, 1.0 + g["dlret_used"].fillna(0.0), 1.0)
    gross = g["tri1"] / g["tri0"] * factor
    g["implied_log"] = np.log(g["value"] / g["prc0"])
    g["realized_log"] = np.log(np.where(gross > 0, gross, np.nan))
    return g[["estimid", "amaskcd", "permno", "anndats", "implied_log", "realized_log"]]


def eval_panel(t: pd.DataFrame, px: pd.DataFrame, dl: pd.DataFrame,
               months: pd.PeriodIndex) -> tuple[pd.DataFrame, dict]:
    """One row per (month, permno, broker's latest active target)."""
    t = _asof(t, px, "anndats", ["cfacpr"], PRICE_TOL_DAYS, suffix="_ann")
    dlmap = dl.set_index("permno")
    frames, stats = [], {"contaminated_excluded": 0, "no_entry_price": 0, "missing_months": []}
    last_px = px["date"].max()
    for m in months:
        cut = m.to_timestamp(how="start") - pd.Timedelta(days=1)
        act = t[(t["anndats"] > cut - pd.Timedelta(days=STALE_DAYS)) & (t["anndats"] <= cut)]
        act = act.sort_values("anndats").drop_duplicates(["permno", "estimid", "amaskcd"], keep="last")
        act = act.drop_duplicates(["permno", "estimid"], keep="last")
        sl = px[(px["date"] <= cut) & (px["date"] > cut - pd.Timedelta(days=PRICE_TOL_DAYS))]
        c = sl.groupby("permno").last()[["prc", "cfacpr", "shrout"]]
        entry_from = cut + pd.Timedelta(days=ENTRY_LAG_DAYS)
        en = px[(px["date"] >= entry_from) & (px["date"] < entry_from + pd.Timedelta(days=10))]
        en = en.groupby("permno").first()[["date", "tri"]].rename(columns={"date": "edate", "tri": "tri_e"})
        exit_from = entry_from + pd.DateOffset(months=1)
        if exit_from > last_px:
            stats["missing_months"].append(str(m))
            continue
        ex = px[(px["date"] >= exit_from) & (px["date"] < exit_from + pd.Timedelta(days=10))]
        ex = ex.groupby("permno").first()[["tri"]].rename(columns={"tri": "tri_x"})
        a = act.join(c, on="permno").join(en, on="permno").join(ex, on="permno")
        a = a[a["prc"].notna()]
        bad = a["cfacpr_ann"].notna() & (a["cfacpr_ann"] != a["cfacpr"])
        stats["contaminated_excluded"] += int(bad.sum())
        a = a[~bad]
        stats["no_entry_price"] += int(a["tri_e"].isna().sum())
        a = a[a["tri_e"].notna()].copy()
        # the exit: CRSP ret compounding, or the last bar x (1 + dlret) on a delisting
        dls = a["permno"].map(dlmap["dlstdt"]) if len(dlmap) else pd.Series(pd.NaT, index=a.index)
        dlr = a["permno"].map(dlmap["dlret_used"]) if len(dlmap) else pd.Series(np.nan, index=a.index)
        died = dls.notna() & (dls > a["edate"]) & (dls <= exit_from)
        if died.any():
            lastbar = px[(px["date"] <= exit_from) & px["permno"].isin(a.loc[died, "permno"])]
            lb = lastbar.groupby("permno")["tri"].last()
            a.loc[died, "tri_x"] = a.loc[died, "permno"].map(lb) * (1.0 + dlr[died].fillna(0.0))
        a["fwd_ret"] = a["tri_x"] / a["tri_e"] - 1.0
        a["upside"] = a["value"] / a["prc"] - 1.0
        a["mcap"] = a["prc"] * a["shrout"] * 1000.0
        a["month"] = str(m)
        frames.append(a[["month", "permno", "estimid", "amaskcd", "upside", "fwd_ret", "mcap"]])
    return pd.concat(frames, ignore_index=True), stats


def _lint_prereg() -> dict:
    lint = PREREG.parent.parent / "scripts" / "lint_prereg.py"
    if not lint.exists():
        return {"status": "LINTER_ABSENT", "path": str(lint)}
    try:
        r = subprocess.run([sys.executable, str(lint), str(PREREG)], cwd=str(PREREG.parent.parent),
                           capture_output=True, text=True, timeout=120)
        return {"status": "OK" if r.returncode == 0 else f"RC_{r.returncode}",
                "tail": (r.stdout + r.stderr)[-600:]}
    except Exception as e:                             # noqa: BLE001 -- recorded
        return {"status": f"FAILED: {type(e).__name__}: {e}"}


def _prereg_hash() -> str | None:
    import hashlib
    return hashlib.sha256(PREREG.read_bytes()).hexdigest()[:16] if PREREG.exists() else None


def run_registered() -> dict:
    t0 = datetime.now(timezone.utc)
    receipt: dict = {"trial": "ANALYST-SKILL-1", "prereg": str(PREREG),
                     "prereg_sha256_16": _prereg_hash(), "lint": _lint_prereg(),
                     "instrument": "tr_ibes.ptgdetu (WRDS bulk parquet on disk) + CRSP dsf + dsedelist",
                     "instrument_matches_registration": True, "started_utc": t0.isoformat()}
    print("  lint:", receipt["lint"]["status"], flush=True)
    t = load_targets("2012-06-01", "2024-12-31")
    print(f"  targets (US, 12m, USD, linked): {len(t):,}", flush=True)
    px = load_prices(2012, 2024)
    print(f"  CRSP daily rows: {len(px):,}", flush=True)
    dl = load_delist()
    est = t[(t["anndats"] >= EST_START) & (t["anndats"] <= EST_END)]
    grades = grade_targets(est, px, dl)
    print(f"  estimation targets graded: {len(grades):,} of {len(est):,}", flush=True)
    skill, grand, prior = broker_skill(grades, "estimid")
    skill.reset_index().to_parquet(OUT_DIR / "broker_skill.parquet", index=False)
    # skill persistence half-to-half (a SKILL number, not an arm number)
    h1 = grades[grades["anndats"] <= "2015-12-31"]
    h2 = grades[grades["anndats"] > "2015-12-31"]
    s1, _, _ = broker_skill(h1)
    s2, _, _ = broker_skill(h2)
    both = s1[["skill", "n"]].join(s2[["skill", "n"]], lsuffix="_h1", rsuffix="_h2", how="inner")
    both = both[(both["n_h1"] >= 20) & (both["n_h2"] >= 20)]
    receipt["skill_table"] = {
        "brokers_measured": int(len(skill)), "grand_median_skill": round(grand, 5),
        "prior_weight_unmeasured": round(prior, 4),
        "estimation_targets_graded": int(len(grades)),
        "persistence_2013_15_vs_2016_18": {"brokers_n20_both": int(len(both)),
                                           "spearman": round(float(both["skill_h1"].rank().corr(
                                               both["skill_h2"].rank())), 4) if len(both) > 2 else None}}
    months = pd.period_range(EVAL_START, EVAL_END, freq="M")
    panel, stats = eval_panel(t[t["anndats"] >= "2018-06-01"], px, dl, months)
    del px
    receipt["panel"] = {**stats, "rows": int(len(panel)),
                        "months_evaluable": int(panel["month"].nunique()),
                        "months_registered": len(months),
                        "brokers_in_panel": int(panel["estimid"].nunique()),
                        "share_panel_rows_measured_broker": round(float(
                            panel["estimid"].isin(skill.index).mean()), 4)}
    print(f"  eval panel: {len(panel):,} rows, {receipt['panel']['months_evaluable']} months; "
          f"missing {stats['missing_months']}", flush=True)
    res = evaluate(panel, skill["weight"], prior)
    monthly = res.pop("monthly")
    receipt["primary"] = res
    if res["verdict"] != "POWER_FAILED":
        monthly.to_csv(OUT_DIR / "analyst_skill_1_monthly.csv", index=False)
        # REPORT-ONLY: never deciding
        s_clean, _, p_clean = broker_skill(grades[grades["anndats"] <= SENSITIVITY_EST_END])
        r2 = evaluate(panel, s_clean["weight"], p_clean)
        r2.pop("monthly")
        a_skill, _, a_prior = broker_skill(grades, "amaskcd")
        r3 = evaluate(panel.dropna(subset=["amaskcd"]), a_skill["weight"], a_prior, level="amaskcd")
        r3.pop("monthly")
        receipt["report_only"] = {
            "attenuation_diagnostic": attenuation_diagnostic(monthly),
            "sensitivity_skill_from_targets_resolved_before_2019": {
                k: r2.get(k) for k in ("verdict", "delta_ic_mean", "t_nw3", "by_year")},
            "analyst_level_amaskcd": {k: r3.get(k) for k in ("verdict", "delta_ic_mean", "t_nw3", "by_year")},
        }
    # descriptive: target-accuracy skill vs the actor corpus' recommendation reliability
    try:
        from backend.services import pit_features as pf
        actor = pd.read_parquet(REPO / "backend" / "data" / "optimus" / "actor_corpus" / "ibes_graded.parquet",
                                columns=["estimid", "direction", "outcome", "public_at"])
        rel = pf.firm_reliability(actor, pd.Timestamp("2019-01-01"))
        j = skill.join(rel[["edge", "n"]], rsuffix="_rec", how="inner")
        j = j[(j["n"] >= 20) & (j["n_rec"] >= 20)]
        receipt["descriptive_target_skill_vs_rec_reliability"] = {
            "brokers": int(len(j)),
            "spearman": round(float(j["skill"].rank().corr(j["edge"].rank())), 4) if len(j) > 2 else None}
    except Exception as e:                               # noqa: BLE001 -- recorded
        receipt["descriptive_target_skill_vs_rec_reliability"] = f"{type(e).__name__}: {e}"
    # the library rules whose branch this verdict funds or closes (chunk C)
    from backend.services.strategy_library_ext import EXTRA_STRATEGIES
    receipt["informs_rules"] = [r.id for r in EXTRA_STRATEGIES
                                if r.family in ("ibes_skill_weighted", "analyst_leadership")]
    receipt["verdict"] = res["verdict"]
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if not a.run:
        print(__doc__)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    r = run_registered()
    path = OUT_DIR / "analyst_skill_1_receipt.json"
    path.write_text(json.dumps(r, indent=2, default=str))
    p = r["primary"]
    print("\nPOWER GATE:", json.dumps(p.get("power_gate"), default=str))
    if p["verdict"] != "POWER_FAILED":
        print("BY YEAR:", json.dumps(p["by_year"], indent=1))
        print("SIZE SPLIT:", json.dumps(p["size_split"]))
        print("LOYO:", json.dumps(p["leave_one_year_out"]))
        print(f"dIC {p['delta_ic_mean']}  t_NW3 {p['t_nw3']}")
        print("ATTENUATION (report-only):", json.dumps(r["report_only"]["attenuation_diagnostic"]))
    print("VERDICT:", r["verdict"], "\nreceipt:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
