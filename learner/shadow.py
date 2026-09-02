"""The DAILY SHADOW. It scores today's tracker and writes a file. That is all.

ZERO BROKER AUTHORITY, BY CONSTRUCTION
======================================
Nothing in this module can place an order. It has no Alpaca client, no ledger
write, no import from the execution repo. It READS
`aegis-alpha-terminal/state/tracker/<day>.jsonl` -- read-only, never opened for
write -- and it WRITES one JSON file into this repository's data directory.
The execution repo does not import `learner`; ML dependencies stay out of it.

WHY IT REFUSES RATHER THAN GUESSES
==================================
A tracker day file cannot supply every column the research model was trained
on: it has no revision counts, no sector code on the panel's SIC scale, no
3-month or 6-month momentum, no split flag. Median-imputing a third of a
model's inputs and calling the output a prediction is the house failure mode --
code that runs green and silently does nothing useful. Two defences:

1. The shadow scores a champion trained ONLY on `dataset.SHADOW_MAPPABLE`
   columns, so it is never asked for an input it cannot have.
2. It still checks, every day, that enough names carry the CORE inputs, and
   writes `status: REFUSED` with named reasons when they do not. A refusal is a
   finding. A garbage book is not.

TWO MAPPINGS THAT ARE EASY TO GET WRONG, AND ARE PINNED HERE
============================================================
* **`coverage` is a RECOMMENDATION count.** IBES `numrec` counts recommenders.
  The tracker day file carries BOTH `n_analysts_yf` (yfinance's target-estimate
  count, the analogue of IBES `numest`) and `rec_counts` (the recommendation
  histogram). They are different variables and they differ by roughly 1.8x --
  which is exactly how hack6's "requires 4-10 analysts" rule ended up admitting
  1-2-analyst names. `coverage` here is `sum(rec_counts.values())`; `numest` is
  `n_analysts_yf`. Neither is used for the other.
* **`consensus` runs 5 = STRONG BUY.** IBES `meanrec` runs 1 = strong buy and
  the panel converts with `6 - meanrec`. The day file has no mean, so consensus
  is rebuilt from the histogram as `(5*sB + 4*b + 3*h + 2*s + 1*sS) / n`, which
  reproduces the terminal's own published `consensus` exactly (MU 2026-09-02:
  244/58 = 4.207, matching `company_state`). `assert_consensus_scale` refuses
  if a reconstructed value ever lands outside [1, 5].

ONE MAPPING THAT IS AN APPROXIMATION, SAID OUT LOUD
===================================================
The panel's `drawdown_60d` divides an ADJUSTED close by an ADJUSTED 60-session
high. The day file carries raw `close` and raw `high_60d`. Across a split in
the last 60 sessions those are not the same quantity, and the day file has no
split flag to detect it. The value is still used -- refusing every name for a
rare event would be worse -- and `mapping_caveats` in the output names it.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from learner import dataset as D
from learner import models as M
from learner import prior as P

REPO = Path(__file__).resolve().parent.parent
TERMINAL = Path(r"C:\Users\mrthn\aegis-alpha-terminal")
TRACKER_DIR = TERMINAL / "state" / "tracker"
OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
MODEL_DIR = OUT_DIR / "models"

#: hack3's mandate: ten names at 8.3% notional each (83% gross, 17% cash).
SHADOW_K = 10
SHADOW_WEIGHT_PCT = 8.3

#: A name must clear the house execution floor to be in a book at all. Below
#: $3.0m/day the universe rules say OBSERVE_ONLY, and a shadow that ranks
#: unbuyable names is a backtest of something nobody could hold.
MIN_DOLLAR_VOL = 3_000_000.0

#: Refusal thresholds, declared here rather than improvised at the call site.
MIN_SCOREABLE_NAMES = 3 * SHADOW_K
MIN_CORE_COVERAGE = 0.20          # share of the day file that is scoreable
MIN_COLUMN_COVERAGE = 0.80        # share of model columns that are populated

#: A name is SCOREABLE only with all of these. Everything else may be missing.
CORE_FEATURES = ("ratio", "consensus", "coverage", "log_close",
                 "log_market_cap", "log_dollar_vol_20d")

REC_WEIGHTS = {"strongBuy": 5.0, "buy": 4.0, "hold": 3.0, "sell": 2.0, "strongSell": 1.0}


# ------------------------------------------------------------------ reading

def read_tracker_day(day: str) -> tuple[list[dict], dict]:
    """READ-ONLY. Returns (rows, provenance). Never opens the file for write."""
    path = TRACKER_DIR / f"{day}.jsonl"
    prov = {"path": str(path), "exists": path.exists(), "access": "read-only"}
    if not path.exists():
        return [], prov
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    prov["bad_lines"] = prov.get("bad_lines", 0) + 1
    prov["rows"] = len(rows)
    prov["mtime_utc"] = datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return rows, prov


def latest_tracker_day() -> str | None:
    days = sorted(p.stem for p in TRACKER_DIR.glob("*.jsonl")
                  if len(p.stem) == 10 and p.stem[4] == "-")
    return days[-1] if days else None


# ------------------------------------------------------------------ mapping

def assert_consensus_scale(values: pd.Series) -> None:
    """5 = STRONG BUY. A value outside [1, 5] means the histogram was read on
    the wrong scale, which would rank the most HATED names first."""
    v = values.dropna()
    if len(v) and (v.min() < 1.0 - 1e-9 or v.max() > 5.0 + 1e-9):
        raise SystemExit(
            f"REFUSED: reconstructed consensus outside [1,5] "
            f"(min {v.min():.3f}, max {v.max():.3f}). The 5=strong-buy scale is wrong.")


def map_to_features(rows: list[dict], band_map: dict) -> tuple[pd.DataFrame, dict]:
    """Tracker day rows -> the panel's feature columns. Unmappable stays NaN."""
    recs = []
    for r in rows:
        rc = r.get("rec_counts") or {}
        n_rec = float(sum(v for v in rc.values() if isinstance(v, (int, float))))
        score = sum(REC_WEIGHTS[k] * float(rc.get(k, 0) or 0) for k in REC_WEIGHTS)
        recs.append({
            "symbol": r.get("symbol"),
            "close": _f(r.get("close")),
            "mean_target": _f(r.get("mean_target")),
            "target_high": _f(r.get("target_high")),
            "target_low": _f(r.get("target_low")),
            # coverage is a RECOMMENDATION count; numest is a TARGET-estimate
            # count. They differ by ~1.8x and are never substituted.
            "coverage": n_rec if n_rec > 0 else np.nan,
            "consensus": (score / n_rec) if n_rec > 0 else np.nan,
            "numest": _f(r.get("n_analysts_yf")),
            "ret_12m": _f(r.get("ret_12m")),
            "high_60d": _f(r.get("high_60d")),
            "vol_20d": _f(r.get("realised_vol_20d")),
            "market_cap": _f(r.get("market_cap_usd")),
            "dollar_vol_20d": _f(r.get("median_dollar_volume")),
            "sessions": _f(r.get("sessions")),
            "tradable": bool(r.get("tradable", False)),
            "sector_label_raw": r.get("sector"),
            "days_to_catalyst": _f(r.get("days_to_catalyst")),
        })
    df = pd.DataFrame(recs)
    if df.empty:
        return df, {"note": "no rows"}

    assert_consensus_scale(df["consensus"])

    df["ratio"] = df["mean_target"] / df["close"].where(df["close"] > 0)
    df["upside"] = df["ratio"] - 1.0                      # THE UNIT: ratio - 1
    df["log_ratio"] = np.log(df["ratio"].where(df["ratio"] > 0))
    df["log_coverage"] = np.log1p(df["coverage"].clip(lower=0))
    df["disagreement"] = ((df["target_high"] - df["target_low"])
                          / df["mean_target"].replace(0, np.nan))
    # Raw close over raw 60-session high: an approximation across a split.
    df["drawdown_60d"] = df["close"] / df["high_60d"].where(df["high_60d"] > 0) - 1.0
    df["log_dollar_vol_20d"] = np.log1p(df["dollar_vol_20d"].clip(lower=0))
    df["log_market_cap"] = np.log(df["market_cap"].where(df["market_cap"] > 0))
    df["log_close"] = np.log(df["close"].where(df["close"] > 0))

    df["band"] = P.effective_band(df["ratio"], df["close"], df["coverage"]).values
    df["band_code"] = df["band"].map(band_map).astype("float64")
    df["prior_1m"] = P.horizon_prior(df["ratio"], df["close"], df["coverage"], 1).values
    df["month"] = "shadow"                                # one cross-section

    # Cross-sectional percentile ranks, over TODAY's cross-section.
    for f in D.RANKED:
        if f in df.columns:
            df[D.ranked_name(f)] = df[f].rank(pct=True)

    unmapped = [c for c in D.FEATURES_CONTINUOUS if c not in df.columns]
    caveats = {
        "unmappable_from_a_tracker_day_file": unmapped,
        "drawdown_60d": "raw close / raw 60-session high; the panel uses ADJUSTED prices. "
                        "Wrong across a split inside 60 sessions, and the day file carries "
                        "no split flag to detect one.",
        "coverage": "sum(rec_counts) -- a RECOMMENDATION count, the IBES numrec analogue",
        "numest": "n_analysts_yf -- a TARGET-ESTIMATE count, the IBES numest analogue",
        "sector": "the tracker's sector is an industry string (yfinance); the panel's is a "
                  "SIC division. NOT mapped -- a wrong code is worse than a missing one.",
    }
    return df, caveats


def _f(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


# ------------------------------------------------------------------ scoring

def load_champion(tag: str = "shadow") -> dict:
    import joblib
    path = MODEL_DIR / f"champion_{tag}.joblib"
    if not path.exists():
        raise SystemExit(f"REFUSED: no sealed model at {path}. "
                         "Run `python -m scripts.learner_run` first.")
    return joblib.load(path)


def _band_map() -> dict:
    if not D.SCHEMA_RECEIPT.exists():
        raise SystemExit(f"REFUSED: {D.SCHEMA_RECEIPT} missing -- the band code mapping "
                         "lives there and guessing it would mislabel every name.")
    rec = json.loads(D.SCHEMA_RECEIPT.read_text(encoding="utf-8"))
    return rec["build"]["categorical_maps"]["band"]


def coverage_report(df: pd.DataFrame, cols: list[str]) -> dict:
    core_ok = pd.Series(True, index=df.index)
    for c in CORE_FEATURES:
        core_ok &= df[c].notna() if c in df.columns else False
    present = [c for c in cols if c in df.columns]
    missing_cols = [c for c in cols if c not in df.columns]
    filled = {c: round(float(df[c].notna().mean()), 4) for c in present}
    populated = sum(1 for c in present if df[c].notna().mean() >= 0.5)
    return {
        "n_rows": int(len(df)),
        "n_scoreable": int(core_ok.sum()),
        "core_coverage": round(float(core_ok.mean()), 4) if len(df) else 0.0,
        "column_coverage": round(populated / max(1, len(cols)), 4),
        "columns_absent_entirely": missing_cols,
        "fill_rate_by_column": filled,
        "_core_ok": core_ok,
    }


def build_shadow_book(day: str | None = None, k: int = SHADOW_K,
                      weight_pct: float = SHADOW_WEIGHT_PCT,
                      tag: str = "shadow") -> dict:
    """Score today's tracker with the sealed champion. Returns the book dict --
    or a REFUSED dict with reasons. Places NOTHING either way."""
    day = day or latest_tracker_day()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: dict = {
        "artefact": "AEGIS_LEARNER_SHADOW_BOOK",
        "licence": "PRODUCT_EXPERIMENT",
        "broker_authority": "NONE -- this file is written, never sent. No order path imports "
                            "learner/. The execution repo does not depend on this package.",
        "day": day, "generated_at_utc": now,
        "mandate": {"k": k, "weight_pct_each": weight_pct,
                    "gross_pct": round(k * weight_pct, 1),
                    "cash_pct": round(100.0 - k * weight_pct, 1),
                    "source": "hack3's mandate: ten names at 8.3% notional"},
    }
    reasons: list[str] = []
    if day is None:
        return {**out, "status": "REFUSED",
                "reasons": ["no tracker day file exists at all"]}

    try:
        champ = load_champion(tag)
    except SystemExit as exc:
        return {**out, "status": "REFUSED", "reasons": [str(exc)]}
    out["model"] = {
        "kind": champ["kind"], "arm": champ["arm"],
        "horizon_months": champ["horizon_months"],
        "model_vintage_sha256_16": champ.get("model_vintage_sha256_16"),
        "prediction_unit": M.prediction_unit(champ["kind"]),
        "schema_hash": champ.get("schema_hash"),
        "prior_version": champ.get("prior_version"),
        "trained_rows": champ.get("trained_rows"),
        "trained_through_month": champ.get("trained_through_month"),
        "trained_at_utc": champ.get("trained_at_utc"),
    }
    if champ.get("schema_hash") != D.schema_hash(shadow_only=True):
        reasons.append(
            f"schema hash mismatch: model was sealed against {champ.get('schema_hash')}, "
            f"the current shadow schema is {D.schema_hash(shadow_only=True)}. Retrain.")

    rows, prov = read_tracker_day(day)
    out["source"] = prov
    if not rows:
        return {**out, "status": "REFUSED",
                "reasons": reasons + [f"tracker day file for {day} is missing or empty"]}

    df, caveats = map_to_features(rows, _band_map())
    out["mapping_caveats"] = caveats
    cols = list(champ["feature_cols"])
    cov = coverage_report(df, cols)
    core_ok = cov.pop("_core_ok")
    out["feature_coverage"] = cov

    if cov["columns_absent_entirely"]:
        reasons.append(f"model columns absent from the mapped frame: "
                       f"{cov['columns_absent_entirely']}")
    if cov["n_scoreable"] < MIN_SCOREABLE_NAMES:
        reasons.append(f"only {cov['n_scoreable']} scoreable names "
                       f"(need >= {MIN_SCOREABLE_NAMES})")
    if cov["core_coverage"] < MIN_CORE_COVERAGE:
        reasons.append(f"core feature coverage {cov['core_coverage']:.2%} "
                       f"< {MIN_CORE_COVERAGE:.0%}")
    if cov["column_coverage"] < MIN_COLUMN_COVERAGE:
        reasons.append(f"column coverage {cov['column_coverage']:.2%} "
                       f"< {MIN_COLUMN_COVERAGE:.0%}")
    if reasons:
        return {**out, "status": "REFUSED", "reasons": reasons,
                "note": "a refusal is a finding. No book is better than a garbage book."}

    scoreable = df[core_ok].copy()
    # The champion may be the classifier head, whose output is a PROBABILITY.
    # It is stored under `score` with its unit named, never as a return: adding
    # a probability to the prior would make a number with no unit that still
    # sorts, which is the shape of every silent scale bug in this repo.
    is_prob = champ["kind"] == M.CLASSIFIER
    scoreable["score"] = M.predict_with(
        champ["kind"], champ["model"], champ["arm"], scoreable, cols,
        champ["horizon_months"])

    # Execution gates. These CUT the book; they never re-rank it, and each one
    # reports what it removed rather than silently deleting names.
    gates = {"start": int(len(scoreable))}
    liquid = scoreable[scoreable["dollar_vol_20d"] >= MIN_DOLLAR_VOL]
    gates["removed_below_3m_dollar_vol"] = int(len(scoreable) - len(liquid))
    tradable = liquid[liquid["tradable"]]
    gates["removed_not_tradable"] = int(len(liquid) - len(tradable))
    gates["eligible"] = int(len(tradable))
    out["execution_gates"] = gates

    if len(tradable) < k:
        return {**out, "status": "REFUSED",
                "reasons": [f"only {len(tradable)} names survive the execution gates; "
                            f"the mandate needs {k}"]}

    picks = tradable.sort_values(["score", "symbol"], ascending=[False, True]).head(k)
    out["status"] = "OK"
    out["score_unit"] = M.prediction_unit(champ["kind"])
    out["holdings"] = [{
        "symbol": r.symbol,
        "weight_pct": weight_pct,
        "score": round(float(r.score), 5),
        "engine_prior_1m": round(float(r.prior_1m), 5),
        # Only defined when the score IS an expected excess return. A
        # probability minus a return is not a delta.
        "learner_delta_vs_prior": (None if is_prob
                                   else round(float(r.score - r.prior_1m), 5)),
        "band": r.band,
        "ratio": _r(r.ratio), "upside": _r(r.upside), "consensus": _r(r.consensus),
        "coverage": _r(r.coverage), "close": _r(r.close),
        "median_dollar_volume": _r(r.dollar_vol_20d, 0),
        "market_cap_usd": _r(r.market_cap, 0),
        "sector_label_raw": r.sector_label_raw,
    } for r in picks.itertuples()]
    out["book_summary"] = {
        "mean_score": round(float(picks["score"].mean()), 5),
        "score_unit": M.prediction_unit(champ["kind"]),
        "mean_engine_prior_1m": round(float(picks["prior_1m"].mean()), 5),
        "bands_held": picks["band"].value_counts().to_dict(),
        "n_toxic_band_held": int((picks["band"] == "toxic_ge_5").sum()),
        "worst_case_if_every_name_stops_at_-3pct":
            round(-0.03 * k * weight_pct, 3),
        "worst_case_note": (
            f"{k} names x {weight_pct}% x 3% stop. Gross is {k * weight_pct:.1f}% of equity; "
            "a modelled gap is many times a stop and is not bounded by it."),
    }
    return out


def _r(v, nd: int = 4):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def write_shadow_book(book: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"shadow_book_{book.get('day')}.json"
    path.write_text(json.dumps(book, indent=2, default=str), encoding="utf-8")
    return path


__all__ = ["SHADOW_K", "SHADOW_WEIGHT_PCT", "MIN_DOLLAR_VOL", "CORE_FEATURES",
           "read_tracker_day", "latest_tracker_day", "map_to_features",
           "assert_consensus_scale", "load_champion", "coverage_report",
           "build_shadow_book", "write_shadow_book"]
