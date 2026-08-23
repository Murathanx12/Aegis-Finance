"""EVENT-RESPONSE-1 — after the market's first move, does it continue or revert?

WHY THIS QUESTION AND NOT "IS THE NEWS GOOD"
============================================
`ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md` P1.1. Stocks trade on surprise, and by
the time we could act, the obvious part of an earnings surprise is already in the
opening gap. So the tradable question is never "was it a beat" -- it is:

    given the event AND the market's first reaction to it,
    is the rest of the move continuation or reversal?

That is a conditional question, which is the kind a model can learn and a
sentiment score cannot.

WHY IT CAN BE ASKED TODAY, ON DISK, WITH NO NEW PULL
====================================================
`g4/earnings_v1` already carries, per announcement and PIT-validated:

    numeric_expectation, expectation_dispersion, n_estimates, actual
    pre_event_price_runup          the 20 sessions before
    overnight_gap                  THE FIRST MOVE
    market_reaction_tradable       the reaction from the tradable open
    dollar_volume_20d, hl_range_20d, amihud_20d
    analyst_revision_state
    tradable_at                    exchange-calendar validated

Roughly 4,300 events per year, 2006-2019. Forward returns come from CRSP daily,
also on disk.

WHAT IS DELIBERATELY OUT OF SCOPE FOR v1
========================================
* **Intraday horizons.** The roadmap names 30m/1d/2d/5d. TAQ is pulled but
  extracting an intraday reaction path is its own ingestion job, and pretending
  a daily bar answers a 30-minute question would be the wrong world. v1 is
  DAILY: +1, +2, +5 sessions from the tradable open.
* **Options-implied move.** `options_implied_move` is None throughout this
  corpus (the single-name surface was never extracted). It is the single most
  valuable missing feature and it is named here rather than quietly absent.
* **Costs, capacity, turnover.** This is a predictability screen. Whatever it
  finds licenses BUILDING a selector, never a claim of edge.

THE SAMPLE SIZE IS EVENT MONTHS
===============================
CANON §58: `n_effective` counts DATE BLOCKS. Earnings cluster hard into four
seasons a year, so thousands of events resolve on a few hundred distinct days
and share whatever the market did that day. Every split and every interval is by
event month.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
G4 = Path(r"C:\Users\mrthn\Aegis module\data\g4\earnings_v1")
OUT = REPO / "backend" / "data" / "optimus" / "event_response"


SPEC: dict = {
    "trial_id": "EVENT-RESPONSE-1",
    "licence": "PRODUCT_EXPERIMENT (screen — licenses building, never a claim)",
    "question": ("Conditional on an earnings event and the market's FIRST "
                 "reaction to it, is the subsequent move continuation or "
                 "reversal?"),
    "corpus": "g4/earnings_v1 (2006-2019) x CRSP daily",
    "min_estimates": 3,
    "horizons_sessions": [1, 2, 5],
    "first_move": "overnight_gap — prior close to the tradable open",
    "target": ("drift_k = sign(gap) * cumulative excess return over the k "
               "sessions STRICTLY AFTER the event session. POSITIVE = the first "
               "move continued, NEGATIVE = it reversed. Entry is the event "
               "day's CLOSE: CRSP daily returns are close-to-close, so "
               "including the event session would put the gap inside the "
               "target it is signed by and manufacture continuation."),
    "entry_assumption": ("the event day's close. The gap is observable at the "
                         "open, but nobody fills at the open price they are "
                         "still measuring."),
    "excess_vs": "equal-weighted CRSP market over the same sessions",
    "n_effective": "EVENT MONTHS (date blocks) — never events (CANON §58)",
    "splits": "expanding-window by year; train < Y, test = Y, Y from 2012",
    "models": [
        "surprise_only  the published PEAD prior: scaled surprise alone",
        "ridge          all features, linear",
        "lightgbm       all features, trees",
    ],
    "context_reported": ("the UNCONDITIONAL mean drift per horizon — whether "
                         "there is any continuation to predict at all. Reported, "
                         "never an arm: a constant has no cross-sectional rank "
                         "and cannot be scored by rank IC."),
    "primary_metric": ("out-of-sample rank IC of predicted vs realised drift, "
                       "computed WITHIN each event month then averaged"),
    "decision_rule": (
        "BUILD a selector iff the best model (a) has a mean monthly rank IC "
        "whose 95% interval over event months excludes zero after BH-FDR "
        "across every (model, horizon) arm in this run, AND (b) beats the "
        "RIDGE baseline on the same months by more than one paired SE. A "
        "model that cannot beat ridge is not evidence for the model, it is "
        "evidence for the features."),
    "why_relative_not_absolute": (
        "No absolute IC bar is declared because none is defensible at this "
        "unit — the co-coverage screen's 0.01 was a MONTHLY CROSS-SECTIONAL "
        "bar over ~4,000 names and this is a within-event-month rank over a "
        "few hundred. Inventing a number here and clearing it would be the "
        "bar chosen by whoever wanted to pass."),
    "known_missing": {
        "options_implied_move": "None throughout the corpus — never extracted",
        "intraday": "TAQ is pulled but not extracted; 30m is deferred, not answered",
        "guidance_state": "UNKNOWN throughout — ibes.det_guidance is not entitled",
    },
}


def spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────── loading


def load_events() -> pd.DataFrame:
    if not G4.exists():
        sys.exit(f"REFUSED: g4 corpus not found at {G4}")
    rows = []
    for p in sorted(G4.glob("g4_earnings_*.jsonl")):
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    if not rows:
        sys.exit("REFUSED: g4 corpus is empty")
    d = pd.DataFrame(rows)
    d["tradable_at"] = pd.to_datetime(d["tradable_at"], utc=True,
                                      errors="coerce")
    d = d.dropna(subset=["tradable_at"])
    d["event_date"] = d["tradable_at"].dt.tz_localize(None).dt.normalize()
    d["event_month"] = d["event_date"].values.astype("datetime64[M]")
    return d


def link_permno(d: pd.DataFrame) -> pd.DataFrame:
    """IBES ticker -> cusip -> permno, valid at the announcement date."""
    act = pd.read_parquet(WRDS / "bulk" / "ibes__actu_epsus.parquet",
                          columns=["ticker", "cusip", "anndats"])
    act = act.dropna(subset=["cusip"])
    act["anndats"] = pd.to_datetime(act["anndats"])
    # one cusip per ticker-year is enough; a ticker that changed cusip mid-year
    # is rare and resolves to the majority
    act["yr"] = act["anndats"].dt.year
    tick = (act.groupby(["ticker", "yr"])["cusip"]
            .agg(lambda s: s.value_counts().index[0]).reset_index())

    names = pd.read_parquet(WRDS / "bulk" / "crsp__dsenames.parquet",
                            columns=["permno", "ncusip", "namedt", "nameendt"])
    names = names.dropna(subset=["ncusip"])
    names["namedt"] = pd.to_datetime(names["namedt"])
    names["nameendt"] = pd.to_datetime(names["nameendt"])

    d = d.copy()
    d["yr"] = d["event_date"].dt.year
    m = d.merge(tick, left_on=["entity_id", "yr"], right_on=["ticker", "yr"],
                how="left")
    m = m.merge(names, left_on="cusip", right_on="ncusip", how="left")
    m = m[(m["event_date"] >= m["namedt"]) & (m["event_date"] <= m["nameendt"])]
    m["permno"] = m["permno"].astype("int64")
    return m.drop_duplicates(subset=["event_id"])


def forward_returns(permnos: set[int], y0: int, y1: int
                    ) -> tuple[pd.DataFrame, pd.Series]:
    """Per (permno, session) forward excess returns at each declared horizon."""
    frames = []
    for yr in range(y0, y1 + 2):
        p = WRDS / f"crsp_dsf_{yr}.parquet"
        if p.exists():
            f = pd.read_parquet(p, columns=["permno", "date", "ret"])
            frames.append(f[f["permno"].isin(permnos)])
    if not frames:
        sys.exit("REFUSED: no crsp_dsf_*.parquet covering the corpus window")
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    d = d.dropna(subset=["ret"]).sort_values(["permno", "date"])

    # Equal-weighted market, from the same rows, so the benchmark is the same
    # universe rather than an index we happen to have.
    mkt = d.groupby("date")["ret"].mean().rename("mkt")

    d = d.merge(mkt, left_on="date", right_index=True, how="left")
    d["ex"] = d["ret"] - d["mkt"]
    d["sess"] = d.groupby("permno").cumcount()
    for k in SPEC["horizons_sessions"]:
        # STRICTLY AFTER the event session, and this is not a detail.
        #
        # CRSP daily `ret` is CLOSE-TO-CLOSE, so the event session's return
        # already contains the overnight gap. The target is
        # `sign(gap) x forward return`, so including that session would make
        # |gap| contribute POSITIVELY to the target by construction -- a
        # guaranteed "continuation" finding that is pure arithmetic. The first
        # version of this file did exactly that.
        #
        # So the window starts at t+1: entry at the EVENT DAY'S CLOSE, which is
        # also the honest tradable assumption. The gap is observable at the
        # open; nobody fills at the open price they are still measuring.
        inc = (d.groupby("permno")["ex"]
               .transform(lambda s, k=k: s[::-1].rolling(k, min_periods=k)
                          .sum()[::-1]))
        d[f"_inc{k}"] = inc
        d[f"fwd{k}"] = d.groupby("permno")[f"_inc{k}"].shift(-1)
        d = d.drop(columns=[f"_inc{k}"])
    return d, mkt


# ─────────────────────────────────────────────────────────── the frame


#: Features. Every one is knowable at the tradable open — the surprise and its
#: dispersion were published, the run-up and the gap have already happened, and
#: the liquidity measures are trailing 20-day. Nothing here is measured after
#: the point the position would be taken.
FEATURES = [
    "numeric_surprise_pct", "surprise_scaled", "expectation_dispersion",
    "n_estimates", "pre_event_price_runup", "overnight_gap", "abs_gap",
    "gap_vs_runup", "dollar_volume_20d_log", "hl_range_20d", "amihud_20d_log",
    "revision_up", "revision_down", "disclosure_delay_days",
]


def build_frame(ev: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    d = ev.copy()
    for c in ("numeric_surprise_pct", "expectation_dispersion", "n_estimates",
              "pre_event_price_runup", "overnight_gap", "dollar_volume_20d",
              "hl_range_20d", "amihud_20d", "disclosure_delay_days",
              "numeric_surprise"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")

    d = d[d["n_estimates"] >= SPEC["min_estimates"]]
    d = d.dropna(subset=["overnight_gap", "numeric_surprise"])

    # SCALED surprise: a 2-cent miss on a 5-cent estimate is not the same event
    # as a 2-cent miss on a $3 estimate, and dispersion is what the street
    # itself said the uncertainty was.
    disp = d["expectation_dispersion"].replace(0, np.nan)
    d["surprise_scaled"] = (d["numeric_surprise"] / disp).clip(-10, 10)
    d["abs_gap"] = d["overnight_gap"].abs()
    d["gap_vs_runup"] = d["overnight_gap"] - d["pre_event_price_runup"].fillna(0)
    d["dollar_volume_20d_log"] = np.log1p(d["dollar_volume_20d"].clip(lower=0))
    d["amihud_20d_log"] = np.log1p(d["amihud_20d"].clip(lower=0))
    rs = d.get("analyst_revision_state").astype(str)
    d["revision_up"] = (rs == "UP").astype("int8")
    d["revision_down"] = (rs == "DOWN").astype("int8")

    j = d.merge(px[["permno", "date"] + [f"fwd{k}"
                                         for k in SPEC["horizons_sessions"]]],
                left_on=["permno", "event_date"], right_on=["permno", "date"],
                how="inner")

    sign = np.sign(j["overnight_gap"]).replace(0, np.nan)
    for k in SPEC["horizons_sessions"]:
        # THE TARGET. Positive = the first move continued; negative = it
        # reversed. Signing by the gap is what turns a return into an answer to
        # the question actually being asked.
        j[f"drift{k}"] = sign * j[f"fwd{k}"]
    return j.dropna(subset=["drift1"])


# ─────────────────────────────────────────────────────────── evaluation


def _rank_ic(pred: np.ndarray, real: np.ndarray) -> float | None:
    ok = np.isfinite(pred) & np.isfinite(real)
    if ok.sum() < 20:
        return None
    a, b = pred[ok], real[ok]
    if np.all(a == a[0]) or np.all(b == b[0]):
        return None
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def _bh_fdr(pvals: dict, q: float = 0.10) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, thresh = len(items), 0.0
    for i, (_k, pv) in enumerate(items, start=1):
        if pv <= i / m * q:
            thresh = i / m * q
    return {k: (pv <= thresh) for k, pv in items}


def _fit_predict(name, Xtr, ytr, Xte):
    if name == "surprise_only":
        j = FEATURES.index("surprise_scaled")
        return Xte[:, j]
    if name == "ridge":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        mdl = make_pipeline(SimpleImputer(strategy="median"),
                            StandardScaler(), Ridge(alpha=10.0))
        mdl.fit(Xtr, ytr)
        return mdl.predict(Xte)
    if name == "lightgbm":
        import lightgbm as lgb
        mdl = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05,
                                num_leaves=31, min_child_samples=50,
                                subsample=0.8, colsample_bytree=0.8,
                                random_state=0, verbose=-1)
        mdl.fit(Xtr, ytr)          # LightGBM handles NaN natively
        return mdl.predict(Xte)
    raise ValueError(name)


def run() -> dict:
    from scipy import stats

    print(f"spec_hash {spec_hash()}", flush=True)
    ev = load_events()
    print(f"  {len(ev):,} raw events", flush=True)
    ev = link_permno(ev)
    print(f"  {len(ev):,} linked to a permno", flush=True)
    y0, y1 = int(ev["event_date"].dt.year.min()), int(ev["event_date"].dt.year.max())
    px, _ = forward_returns(set(ev["permno"].unique()), y0, y1)
    fr = build_frame(ev, px)
    print(f"  {len(fr):,} modelled events, "
          f"{fr['event_month'].nunique()} event months", flush=True)

    # CONTEXT: is there anything to predict? Reported, never an arm.
    context = {}
    for k in SPEC["horizons_sessions"]:
        col = fr[f"drift{k}"].dropna()
        by_m = fr.groupby("event_month")[f"drift{k}"].mean().dropna()
        context[f"drift{k}"] = {
            "n_events": int(len(col)),
            "mean_drift": round(float(col.mean()), 6),
            "mean_of_monthly_means": round(float(by_m.mean()), 6),
            "monthly_se": round(float(by_m.std(ddof=1) / np.sqrt(len(by_m))), 6),
            "n_months": int(len(by_m)),
        }

    ics: dict[str, list] = {}
    months: dict[str, list] = {}
    years = sorted(y for y in fr["event_date"].dt.year.unique() if y >= 2012)
    for k in SPEC["horizons_sessions"]:
        tgt = f"drift{k}"
        for name in ("surprise_only", "ridge", "lightgbm"):
            arm = f"{name}@{k}d"
            ics[arm], months[arm] = [], []
            for Y in years:
                tr = fr[(fr["event_date"].dt.year < Y) & fr[tgt].notna()]
                te = fr[(fr["event_date"].dt.year == Y) & fr[tgt].notna()]
                if len(tr) < 2000 or len(te) < 200:
                    continue
                Xtr = tr[FEATURES].to_numpy(dtype="float64")
                Xte = te[FEATURES].to_numpy(dtype="float64")
                try:
                    pred = _fit_predict(name, Xtr, tr[tgt].to_numpy(), Xte)
                except Exception as e:                          # noqa: BLE001
                    print(f"    {arm} {Y}: {type(e).__name__}: {e}", flush=True)
                    continue
                t2 = te.assign(_p=pred)
                for m, g in t2.groupby("event_month"):
                    ic = _rank_ic(g["_p"].to_numpy(), g[tgt].to_numpy())
                    if ic is not None:
                        ics[arm].append(ic)
                        months[arm].append(str(pd.Timestamp(m).date()))
            print(f"  {arm:22s} {len(ics[arm])} test months", flush=True)

    results, pvals = {}, {}
    for arm, series in ics.items():
        if len(series) < 12:
            results[arm] = {"n_months": len(series), "status": "TOO_FEW_MONTHS"}
            continue
        a = np.array(series)
        mean = float(a.mean())
        se = float(a.std(ddof=1) / np.sqrt(len(a)))
        t = mean / se if se > 0 else 0.0
        pv = float(2 * (1 - stats.t.cdf(abs(t), df=len(a) - 1)))
        results[arm] = {"n_months": len(a), "mean_ic": round(mean, 5),
                        "se": round(se, 5), "t": round(t, 3),
                        "p_two_sided": round(pv, 5),
                        "mde_80pct_power": round(2.80 * se, 5)}
        pvals[arm] = pv
    for arm, ok in _bh_fdr(pvals).items():
        results[arm]["bh_fdr_survives"] = bool(ok)

    def paired(a: str, b: str) -> dict | None:
        ma = dict(zip(months.get(a, []), ics.get(a, [])))
        mb = dict(zip(months.get(b, []), ics.get(b, [])))
        common = sorted(set(ma) & set(mb))
        if len(common) < 12:
            return None
        d = np.array([ma[m] - mb[m] for m in common])
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        mean = float(d.mean())
        return {"n_months": len(d), "mean_diff": round(mean, 6),
                "se": round(se, 6), "t": round(mean / se, 3) if se else 0.0,
                "beats_by_more_than_1se": bool(mean > se)}

    comparisons = {}
    for k in SPEC["horizons_sessions"]:
        comparisons[f"lightgbm_vs_ridge@{k}d"] = paired(f"lightgbm@{k}d",
                                                        f"ridge@{k}d")
        comparisons[f"ridge_vs_surprise_only@{k}d"] = paired(
            f"ridge@{k}d", f"surprise_only@{k}d")

    passing = [a for a, r in results.items()
               if r.get("bh_fdr_survives") and r.get("mean_ic", 0) > 0]
    beats_ridge = [k for k, v in comparisons.items()
                   if k.startswith("lightgbm_vs_ridge") and v
                   and v["beats_by_more_than_1se"]]
    verdict = "BUILD" if passing and beats_ridge else (
        "FEATURES_ONLY" if passing else "STOP")

    receipt = {
        "trial_id": SPEC["trial_id"], "spec_hash": spec_hash(), "spec": SPEC,
        "n_events_modelled": int(len(fr)),
        "n_event_months": int(fr["event_month"].nunique()),
        "n_effective": int(fr["event_month"].nunique()),
        "context_unconditional_drift": context,
        "results": results, "paired_comparisons": comparisons,
        "arms_passing": passing,
        "verdict": verdict,
        "verdict_meaning": {
            "BUILD": "an arm cleared BH-FDR AND beat ridge — a selector is licensed",
            "FEATURES_ONLY": ("an arm cleared BH-FDR but nothing beat ridge. The "
                              "FEATURES carry the signal, the model does not add "
                              "to it — build the linear version, not the tree one"),
            "STOP": "nothing survived; earnings-response prediction is not licensed",
        }[verdict],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "event_response_receipt.json").write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "spec"},
                     indent=2, default=str))
