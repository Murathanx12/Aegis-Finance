"""SELF-WRITTEN RULES AND WEIGHTS, ADJUDICATED BY THE DATA (CH-32 night, 2026-11-11).

The owner's question: *"what about the agentic workflow, LLM or AI that writes
its own weights or skills?"* This harness is the smallest closed loop that
answers it on data we already own, without letting the model grade itself:

    PROPOSE  (train only)  the model reads AGGREGATED tables of where the frozen
                           forecasts were right and wrong, and writes rules in a
                           strict JSON schema: a condition over fields that exist
                           AT FORECAST TIME, and one action out of
                           {reweight a forecaster, shrink confidence, abstain}.
                           The same number of rules comes from a greedy search
                           over the same schema (no LLM) and from a random-rule
                           control.
    FREEZE                 every rule is hashed before any validation row is read.
    SELECT   (validation)  forward selection over the frozen candidates.
    REPORT   (held out)    once: change in Brier versus no rules, per source, with
                           n, by month, leave-one-month-out and a block bootstrap.

"Writes its own weights" is the second experiment: forecaster weights fitted on
train with the reputation layer's own code (`forecast_reputation.tune` +
`weights`, the stacking the nightly refit uses) and a per-cell recalibration,
frozen and scored on held-out versus equal weights and investigator-only.

THE SPLIT, AND WHY IT IS STRICT
-------------------------------
`train`      = graded rows RESOLVED before T1 (so every training outcome was
               knowable at T1; the embargo is the horizon itself).
`validation` = rows MADE in [T1, T2) and RESOLVED before T2.
`held_out`   = rows MADE on or after T2 and graded in the snapshot.
A forecast made before T1 that resolves after T1 is in NO split (embargoed),
and the count of such rows is printed. Bucket edges (volatility, momentum,
liquidity) are fitted on train and applied unchanged to later splits.

THE SCORE
---------
The grader's proper scoring rule: Brier, with skill = 1 - Brier / climatology
(`forecast_reputation._score`). Forecasts are pooled per QUESTION (ticker,
observable, horizon, threshold, benchmark, day: `forecast_reputation.QUESTION_COLS`)
by the logit average `forecast_reputation.pool` uses, so a reweight changes the
pooled answer and an abstention hands the question to the train base rate.

Licence: PRODUCT_EXPERIMENT. Leaders are chosen after the fact; nothing here is
a skill claim, and nothing here can reach an order.

    python -m learner.self_rule_lab --ledger <snapshot.jsonl> --out <dir> [--llm]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SCHEMA = "self-rule-lab-1.0.0"

# --------------------------------------------------------------------------
# The experiment contract. These are hashed into every receipt: changing one
# is a different experiment, not a tuning step.
# --------------------------------------------------------------------------
T1_DEFAULT = "2026-09-28"
T2_DEFAULT = "2026-10-13"
N_RULES_DEFAULT = 12
MIN_SUPPORT_ROWS = 100          # a rule must fire on this many train rows ...
MIN_SUPPORT_DAYS = 3            # ... spread over this many forecast days
MAX_CONDITIONS = 3
SHRINK_GRID = (0.25, 0.5, 0.75)
REWEIGHT_GRID = (0.25, 0.5, 2.0, 4.0)
RANDOM_CONTROL_DRAWS = 200
BOOTSTRAP_DRAWS = 1000
SEED = 20261111

ACTIONS = ("reweight", "shrink", "abstain")
OPS = ("eq", "in", "gte", "lte", "between")

#: Fields a rule may condition on. Every one exists when the forecast is made.
CATEGORICAL_FIELDS = ("family", "klass", "arm", "observable", "event_type",
                      "model", "p_side", "sector")
NUMERIC_FIELDS = ("horizon_days", "p", "p_extremity", "vol_q", "mom_q", "liq_q",
                  "weekday", "belief_change_abs")
RULE_FIELDS = CATEGORICAL_FIELDS + NUMERIC_FIELDS

#: Known only after the outcome. A condition on any of these is refused by name
#: (`rule_distillation.LEAKED_OUTCOME_FIELDS` plus this frame's own outcome columns).
FRAME_OUTCOME_FIELDS = frozenset({"y", "ret", "rel_ret", "resolved_on",
                                  "realised_return", "n_bars", "benchmark_return"})


def _leaked_fields() -> frozenset:
    from learner.rule_distillation import LEAKED_OUTCOME_FIELDS
    return frozenset(LEAKED_OUTCOME_FIELDS) | FRAME_OUTCOME_FIELDS


def contract() -> dict:
    return {"schema": SCHEMA, "t1": T1_DEFAULT, "t2": T2_DEFAULT,
            "n_rules": N_RULES_DEFAULT, "min_support_rows": MIN_SUPPORT_ROWS,
            "min_support_days": MIN_SUPPORT_DAYS, "max_conditions": MAX_CONDITIONS,
            "shrink_grid": SHRINK_GRID, "reweight_grid": REWEIGHT_GRID,
            "random_draws": RANDOM_CONTROL_DRAWS, "bootstrap": BOOTSTRAP_DRAWS,
            "seed": SEED, "fields": RULE_FIELDS, "actions": ACTIONS,
            "score": "Brier on question-pooled forecasts; skill = 1 - Brier/clim "
                     "(forecast_reputation._score)"}


def contract_hash(c: dict | None = None) -> str:
    return hashlib.sha256(json.dumps(c if c is not None else contract(), sort_keys=True,
                                     default=str).encode()).hexdigest()[:16]


class LabRefused(RuntimeError):
    """The harness will not report a number it cannot support."""


# ==========================================================================
# 1. THE FRAME: one row per graded forecast, forecast-time features only
# ==========================================================================
_KLASS = {"investigator": "investigator", "review": "review",
          "news_digest": "news_digest", "source": "other", "thesis_card": "other",
          "why_moved": "other", "book": "other", "base_rate": "other",
          "headline_arena": "other", "promise": "other"}


def _family(spec: Any) -> str:
    return str(spec or "").split(":")[0] or "unknown"


def _event_type(r: dict) -> str:
    """A typed event tag from fields written AT forecast time."""
    fam = _family(r.get("specialist"))
    thesis = str(r.get("thesis") or "")
    if fam == "news_digest" and thesis.startswith("["):
        tag = thesis[1:thesis.find("]")] if "]" in thesis else ""
        return "news:" + (tag.split(",")[0].strip().replace(" ", "_") or "untagged")
    if fam == "investigator":
        bc = r.get("belief_change")
        try:
            return "inv:updated" if abs(float(bc)) > 1e-9 else "inv:no_update"
        except (TypeError, ValueError):
            return "inv:unknown"
    if fam == "review":
        return "review:" + ("no_change" if "no change" in thesis else "label_move")
    return "none"


def sector_map() -> dict[str, str]:
    """The only ticker -> sector map in the repo (config `sector_stocks`)."""
    try:
        from backend.config import config as C
        sec = (C.get("stock_universe", {}) or {}).get("sector_stocks", {})
    except Exception:                                            # noqa: BLE001
        sec = {}
    out: dict[str, str] = {}
    for s, tickers in (sec or {}).items():
        for t in tickers:
            out[str(t)] = str(s)
    return out


def frame_from_rows(rows: Iterable[dict], *, sectors: dict[str, str] | None = None
                    ) -> pd.DataFrame:
    """Graded, un-voided, scorable rows -> the frame. Same admission as the
    grader (`forecast_reputation._outcome01`, p in [0, 1])."""
    from backend.services import forecast_reputation as FR
    sectors = sectors if sectors is not None else {}
    held = getattr(FR, "_PREMATURE_ID_HASHES", frozenset())
    out = []
    for r in rows:
        if r.get("void_reason"):
            continue
        # the 214 rows graded early on 2026-10-14 (held out of every refit until an
        # attended regrade) are held out here too, by the refit's own fingerprints
        if held and hashlib.blake2b(str(r.get("prediction_id")).encode(),
                                    digest_size=16).digest() in held:
            continue
        y = FR._outcome01(r.get("outcome"))
        p = FR._num(r.get("probability"))
        if y is None or not (0.0 <= p <= 1.0):
            continue
        fam = _family(r.get("specialist"))
        bc = FR._num(r.get("belief_change"))
        out.append({
            "row_id": str(r.get("prediction_id") or ""),
            "arm": str(r.get("specialist")), "family": fam,
            "klass": _KLASS.get(fam, "personas"),
            "observable": str(r.get("observable")),
            "horizon_days": FR._num(r.get("horizon_days")),
            "threshold": str(r.get("threshold")), "benchmark": str(r.get("benchmark")),
            "ticker": str(r.get("ticker")), "p": p, "y": y,
            "made_at": r.get("made_at"),
            "resolved_on": str(r.get("resolved_at") or r.get("graded_at") or "")[:10],
            "model": str(r.get("model")), "event_type": _event_type(r),
            "belief_change_abs": abs(bc) if math.isfinite(bc) else np.nan,
            "sector": sectors.get(str(r.get("ticker")), "unknown"),
        })
    g = pd.DataFrame(out)
    if g.empty:
        raise LabRefused("no graded, scorable rows in the ledger")
    g["made_at"] = pd.to_datetime(g["made_at"], utc=True, errors="coerce", format="ISO8601")
    g = g[g["made_at"].notna()].copy()
    g["made_day"] = g["made_at"].dt.strftime("%Y-%m-%d")
    g["month"] = g["made_day"].str[:7]
    g["weekday"] = g["made_at"].dt.weekday.astype(float)
    g["p_extremity"] = (g["p"] - 0.5).abs()
    g["p_side"] = np.where(g["p"] > 0.5, "above_half",
                           np.where(g["p"] < 0.5, "below_half", "half"))
    from backend.services import forecast_reputation as FR
    g["qid"] = g.groupby(list(FR.QUESTION_COLS), dropna=False, sort=False).ngroup()
    return g.reset_index(drop=True)


def attach_bar_features(g: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Trailing 63-session vol, 20-session return and 20-session median dollar
    volume, from bars dated STRICTLY BEFORE the forecast day (no same-day bar:
    a forecast made pre-open must not see that session's close)."""
    need = {"symbol", "date", "close", "volume"}
    if bars is None or bars.empty or not need <= set(bars.columns):
        g = g.copy()
        g["vol63"] = np.nan
        g["mom20"] = np.nan
        g["dvol20"] = np.nan
        return g
    b = bars[bars["symbol"].isin(set(g["ticker"]))][["symbol", "date", "close", "volume"]].copy()
    b["date"] = pd.to_datetime(b["date"]).dt.tz_localize(None).dt.normalize()
    b = b.sort_values(["symbol", "date"])
    lr = np.log(b["close"]).groupby(b["symbol"]).diff()
    b["vol63"] = lr.groupby(b["symbol"]).transform(lambda s: s.rolling(63, min_periods=42).std())
    b["mom20"] = b.groupby("symbol")["close"].transform(lambda s: s / s.shift(20) - 1.0)
    b["dvol20"] = (b["close"] * b["volume"]).groupby(b["symbol"]).transform(
        lambda s: s.rolling(20, min_periods=10).median())
    feat = b[["symbol", "date", "vol63", "mom20", "dvol20"]].dropna(subset=["date"])
    left = g[["ticker", "made_day"]].copy()
    left["_d"] = pd.to_datetime(left["made_day"]).astype("datetime64[ns]")
    left["_i"] = np.arange(len(left))
    left = left.sort_values("_d")
    feat = feat.rename(columns={"symbol": "ticker", "date": "_d"})
    feat["_d"] = feat["_d"].astype("datetime64[ns]")
    feat = feat.sort_values("_d")
    m = pd.merge_asof(left, feat, on="_d", by="ticker", direction="backward",
                      allow_exact_matches=False)
    m = m.sort_values("_i")
    g = g.copy()
    for c in ("vol63", "mom20", "dvol20"):
        g[c] = m[c].to_numpy()
    return g


# ==========================================================================
# 2. THE SPLIT
# ==========================================================================
@dataclass
class Split:
    train: pd.DataFrame
    validation: pd.DataFrame
    held_out: pd.DataFrame
    meta: dict


def split_frame(g: pd.DataFrame, t1: str = T1_DEFAULT, t2: str = T2_DEFAULT) -> Split:
    if not t1 < t2:
        raise LabRefused(f"t1 {t1} must precede t2 {t2}")
    made, res = g["made_day"], g["resolved_on"]
    tr = (made < t1) & (res < t1) & (res != "")
    va = (made >= t1) & (made < t2) & (res < t2) & (res != "")
    ho = made >= t2
    embargo = (~tr & ~va & ~ho)
    meta = {"t1": t1, "t2": t2, "n_train": int(tr.sum()), "n_validation": int(va.sum()),
            "n_held_out": int(ho.sum()), "n_embargoed": int(embargo.sum()),
            "rule": ("train: made<T1 and resolved<T1; validation: T1<=made<T2 and "
                     "resolved<T2; held-out: made>=T2; everything else embargoed")}
    for name, m in (("train", tr), ("validation", va), ("held_out", ho)):
        sub = g[m]
        meta[f"{name}_days"] = [sub["made_day"].min(), sub["made_day"].max()] if len(sub) else None
        meta[f"{name}_by_klass"] = {str(k): int(v) for k, v in sub["klass"].value_counts().items()}
    if min(meta["n_train"], meta["n_validation"], meta["n_held_out"]) == 0:
        raise LabRefused(f"an empty split: {meta}")
    return Split(g[tr].copy(), g[va].copy(), g[ho].copy(), meta)


def fit_buckets(train: pd.DataFrame) -> dict:
    """Quintile edges fitted on TRAIN only."""
    edges = {}
    for src in ("vol63", "mom20", "dvol20"):
        x = train[src].dropna()
        edges[src] = [float(v) for v in np.quantile(x, [0.2, 0.4, 0.6, 0.8])] if len(x) >= 50 else None
    return edges


def apply_buckets(g: pd.DataFrame, edges: dict) -> pd.DataFrame:
    g = g.copy()
    for src, dst in (("vol63", "vol_q"), ("mom20", "mom_q"), ("dvol20", "liq_q")):
        e = edges.get(src)
        if not e or src not in g:
            g[dst] = np.nan
            continue
        v = g[src].to_numpy(float)
        q = np.searchsorted(np.asarray(e), v, side="right").astype(float)
        q[~np.isfinite(v)] = np.nan
        g[dst] = q
    return g


def base_rates(train: pd.DataFrame) -> dict:
    by = train.groupby(["observable", "horizon_days"])["y"].mean()
    by_obs = train.groupby("observable")["y"].mean()
    return {"by_cell": {(str(o), float(h)): float(v) for (o, h), v in by.items()},
            "by_observable": {str(k): float(v) for k, v in by_obs.items()},
            "global": float(train["y"].mean())}


def base_rate_for(g: pd.DataFrame, br: dict) -> np.ndarray:
    out = np.empty(len(g))
    for i, (o, h) in enumerate(zip(g["observable"].astype(str), g["horizon_days"].astype(float))):
        out[i] = br["by_cell"].get((o, h), br["by_observable"].get(o, br["global"]))
    return out


# ==========================================================================
# 3. RULES: schema, validation, hashing, vectorised application
# ==========================================================================
def validate_rule(obj: Any) -> tuple[dict | None, str | None]:
    """(rule, refusal). Schema, then the leaked-outcome guard, then field names."""
    if not isinstance(obj, dict):
        return None, "SCHEMA_INVALID: not an object"
    when, action = obj.get("when"), obj.get("action")
    if not isinstance(when, list) or not 1 <= len(when) <= MAX_CONDITIONS:
        return None, f"SCHEMA_INVALID: when must hold 1..{MAX_CONDITIONS} conditions"
    leaked = _leaked_fields()
    clean = []
    for c in when:
        if not isinstance(c, dict) or not {"field", "op", "value"} <= set(c):
            return None, "SCHEMA_INVALID: a condition needs field, op, value"
        f = str(c["field"])
        if f.lower() in leaked:
            return None, f"REJECTED_LEAKED_OUTCOME_FIELD: {f!r} is known only after the outcome"
        if f not in RULE_FIELDS:
            return None, f"SCHEMA_INVALID: field {f!r} not in {list(RULE_FIELDS)}"
        if c["op"] not in OPS:
            return None, f"SCHEMA_INVALID: op {c['op']!r}"
        if c["op"] in ("gte", "lte", "between") and f not in NUMERIC_FIELDS:
            return None, f"SCHEMA_INVALID: numeric op on categorical field {f!r}"
        if c["op"] == "between":
            v = c["value"]
            if not (isinstance(v, (list, tuple)) and len(v) == 2):
                return None, "SCHEMA_INVALID: between needs [lo, hi]"
        if c["op"] == "in" and not isinstance(c["value"], (list, tuple)):
            return None, "SCHEMA_INVALID: in needs a list"
        clean.append({"field": f, "op": c["op"], "value": c["value"]})
    if not isinstance(action, dict) or action.get("type") not in ACTIONS:
        return None, f"SCHEMA_INVALID: action.type must be one of {ACTIONS}"
    a = {"type": action["type"]}
    try:
        if a["type"] == "reweight":
            a["factor"] = float(action.get("factor"))
            if not 0.0 < a["factor"] <= 10.0:
                return None, "SCHEMA_INVALID: reweight factor must be in (0, 10]"
        elif a["type"] == "shrink":
            a["lambda"] = float(action.get("lambda"))
            if not 0.0 <= a["lambda"] < 1.0:
                return None, "SCHEMA_INVALID: shrink lambda must be in [0, 1)"
    except (TypeError, ValueError):
        return None, "SCHEMA_INVALID: action parameter is not a number"
    return {"when": clean, "action": a,
            "rule_text": str(obj.get("rule_text") or "")[:300]}, None


def rule_hash(rule: dict) -> str:
    body = {"when": rule["when"], "action": rule["action"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def freeze(rules: Sequence[dict], source: str) -> list[dict]:
    """Hash each rule and stamp the time BEFORE any validation row is read."""
    t = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return [{**r, "source": source, "rule_hash": rule_hash(r), "frozen_utc": t}
            for r in rules]


def cond_mask(cond: dict, g: pd.DataFrame) -> np.ndarray:
    """Vectorised `rule_distillation.condition_holds`: a MISSING value is False."""
    f, op, v = cond["field"], cond["op"], cond["value"]
    if f not in g.columns:
        return np.zeros(len(g), bool)
    col = g[f]
    present = col.notna().to_numpy()
    if f in CATEGORICAL_FIELDS:
        present &= (col.astype(str) != "None").to_numpy()
    try:
        if op == "eq":
            if f in NUMERIC_FIELDS:
                m = (col.astype(float) == float(v)).to_numpy()
            else:
                m = (col.astype(str) == str(v)).to_numpy()
        elif op == "in":
            if f in NUMERIC_FIELDS:
                m = col.astype(float).isin([float(x) for x in v]).to_numpy()
            else:
                m = col.astype(str).isin([str(x) for x in v]).to_numpy()
        elif op == "gte":
            m = (col.astype(float) >= float(v)).to_numpy()
        elif op == "lte":
            m = (col.astype(float) <= float(v)).to_numpy()
        elif op == "between":
            lo, hi = float(v[0]), float(v[1])
            x = col.astype(float)
            m = ((x >= lo) & (x <= hi)).to_numpy()
        else:
            return np.zeros(len(g), bool)
    except (TypeError, ValueError):
        return np.zeros(len(g), bool)
    return m & present


def rule_mask(rule: dict, g: pd.DataFrame) -> np.ndarray:
    m = np.ones(len(g), bool)
    for c in rule["when"]:
        m &= cond_mask(c, g)
    return m


def apply_rules(g: pd.DataFrame, rules: Sequence[dict], b: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray]:
    """Per-row (weight, probability) after every rule. Order-independent:
    reweights multiply, shrinks compose (p' = b + prod(lambda) (p - b)), an
    abstention sets the weight to zero."""
    w = np.ones(len(g))
    lam = np.ones(len(g))
    for r in rules:
        m = rule_mask(r, g)
        if not m.any():
            continue
        a = r["action"]
        if a["type"] == "abstain":
            w[m] = 0.0
        elif a["type"] == "reweight":
            w[m] *= float(a["factor"])
        elif a["type"] == "shrink":
            lam[m] *= float(a["lambda"])
    p = g["p"].to_numpy(float)
    return w, b + lam * (p - b)


@dataclass
class Questions:
    """Question index precomputed once per split, so scoring is a bincount."""
    qinv: np.ndarray
    y: np.ndarray
    b: np.ndarray
    day: np.ndarray
    month: np.ndarray
    klass: np.ndarray


def questions_of(g: pd.DataFrame, b_row: np.ndarray) -> Questions:
    qid, qinv = np.unique(g["qid"].to_numpy(), return_inverse=True)
    yq = np.zeros(len(qid))
    np.maximum.at(yq, qinv, g["y"].to_numpy(float))
    first = pd.DataFrame({"q": qinv, "b": b_row, "day": g["made_day"].to_numpy(),
                          "month": g["month"].to_numpy(),
                          "klass": g["klass"].to_numpy()}).groupby("q", sort=True).first()
    return Questions(qinv, yq, first["b"].to_numpy(float), first["day"].to_numpy(),
                     first["month"].to_numpy(), first["klass"].to_numpy())


def pooled(Q: Questions, w: np.ndarray, p: np.ndarray) -> np.ndarray:
    """`forecast_reputation.pool` per question (kappa 1); no weight -> base rate."""
    from backend.services.forecast_reputation import _logit, _sigmoid
    lg = _logit(p)
    n = len(Q.y)
    num = np.bincount(Q.qinv, weights=w * lg, minlength=n)
    den = np.bincount(Q.qinv, weights=w, minlength=n)
    has = den > 0
    agg = np.divide(num, den, out=np.zeros_like(num), where=has)
    return np.where(has, _sigmoid(agg), Q.b)


def brier(pq: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((pq - y) ** 2)) if len(y) else float("nan")


def score_rules(g: pd.DataFrame, Q: Questions, b_row: np.ndarray,
                rules: Sequence[dict]) -> np.ndarray:
    w, p = apply_rules(g, rules, b_row)
    return pooled(Q, w, p)


# ==========================================================================
# 4. TABLES FOR THE MODEL (train only)
# ==========================================================================
TABLE_FIELDS = ("klass", "family", "observable", "horizon_days", "event_type",
                "p_side", "vol_q", "mom_q", "liq_q", "model", "sector")


def _cell_stats(sub: pd.DataFrame) -> dict:
    from backend.services.forecast_reputation import _score
    s = _score(sub["p"].to_numpy(float), sub["y"].to_numpy(float))
    return {"n": int(s["n"]), "days": int(sub["made_day"].nunique()),
            "base_rate": round(s["base_rate"], 3), "mean_p": round(float(sub["p"].mean()), 3),
            "brier": round(s["brier"], 4), "skill": (round(s["skill"], 3)
                                                      if np.isfinite(s["skill"]) else None),
            "disc": round(s["disc"], 3) if np.isfinite(s["disc"]) else None}


def train_tables(train: pd.DataFrame, *, min_n: int = 60, max_two_way: int = 40) -> dict:
    """Aggregates of where train forecasts were right and wrong. Nothing here is
    computed from a validation or held-out row -- the caller passes train only,
    and `assert_train_only` checks the dates."""
    one: dict[str, dict] = {}
    for f in TABLE_FIELDS:
        if f not in train.columns:
            continue
        cells = {}
        for k, sub in train.groupby(f, dropna=True):
            if len(sub) >= min_n:
                cells[str(k)] = _cell_stats(sub)
        if cells:
            one[f] = cells
    two = []
    for f in ("observable", "horizon_days", "event_type", "p_side", "vol_q", "mom_q", "liq_q"):
        if f not in train.columns:
            continue
        for (fam, k), sub in train.groupby(["family", f], dropna=True):
            if len(sub) >= min_n:
                two.append({"family": str(fam), "field": f, "value": str(k), **_cell_stats(sub)})
    two.sort(key=lambda r: (r["skill"] if r["skill"] is not None else 0.0))
    two = two[:max_two_way // 2] + two[-(max_two_way // 2):] if len(two) > max_two_way else two
    calib = []
    for (k, pb), sub in train.assign(_pb=(train["p"] * 10).clip(0, 9.99).astype(int) / 10
                                      ).groupby(["klass", "_pb"]):
        if len(sub) >= min_n:
            calib.append({"klass": str(k), "p_from": float(pb), "n": int(len(sub)),
                          "mean_p": round(float(sub["p"].mean()), 3),
                          "hit_rate": round(float(sub["y"].mean()), 3)})
    return {"n_rows": int(len(train)), "made_through": str(train["made_day"].max()),
            "resolved_through": str(train["resolved_on"].max()),
            "one_way": one, "family_two_way": two, "calibration": calib}


def assert_train_only(tables: dict, t1: str) -> None:
    if not (str(tables["made_through"]) < t1 and str(tables["resolved_through"]) < t1):
        raise LabRefused(f"tables carry rows made/resolved on or after T1 {t1}")


LLM_SYSTEM = (
    "You are a forecast-quality analyst. You write rules that adjust a bench of "
    "probability forecasters. You only see aggregated TRAINING statistics. You "
    "reply with ONE JSON object and nothing else.")


def llm_prompt(tables: dict, n_rules: int, field_values: dict) -> str:
    schema = {
        "rules": [{
            "rule_text": "one sentence, why",
            "when": [{"field": "<one of the fields>", "op": "eq|in|gte|lte|between",
                      "value": "<value | [values] | [lo, hi]>"}],
            "action": {"type": "reweight|shrink|abstain",
                       "factor": "reweight only: multiply this forecaster's pooling weight, (0, 10]",
                       "lambda": "shrink only: p' = base + lambda*(p - base), [0, 1)"}}]}
    return (
        f"Below are TRAINING-period statistics for a ledger of probability forecasts "
        f"(Brier score; skill = 1 - Brier/climatology, negative = worse than the base "
        f"rate; disc = mean p on hits minus mean p on misses). Forecasts on the same "
        f"question are pooled by a weighted logit average; an abstained question gets the "
        f"training base rate.\n\n"
        f"Write exactly {n_rules} rules that you expect to LOWER the Brier score on "
        f"FUTURE forecasts. Each rule: 1 to {MAX_CONDITIONS} conditions (all must hold) "
        f"over these forecast-time fields only: {list(RULE_FIELDS)}. "
        f"Categorical values seen in training: {json.dumps(field_values)}. "
        f"vol_q/mom_q/liq_q are training quintiles 0..4 of trailing 63-day volatility, "
        f"20-day return and 20-day dollar volume. p is the forecaster's probability, "
        f"p_extremity = |p - 0.5|. Actions: reweight (factor), shrink (lambda), abstain.\n"
        f"Reply schema: {json.dumps(schema)}\n\n"
        f"TABLES:\n{json.dumps(tables, separators=(',', ':'), default=str)}")


def parse_llm_rules(text: str | None) -> tuple[list[dict], list[str]]:
    from learner.rule_distillation import _parse_json
    obj = _parse_json(text or "")
    if not isinstance(obj, dict) or not isinstance(obj.get("rules"), list):
        return [], ["SCHEMA_INVALID: no {'rules': [...]} object in the reply"]
    good, bad = [], []
    for r in obj["rules"]:
        v, why = validate_rule(r)
        if v is None:
            bad.append(str(why))
        else:
            good.append(v)
    return good, bad


# ==========================================================================
# 5. THE NON-LLM BASELINE AND THE RANDOM CONTROL (same schema, same count)
# ==========================================================================
def _atoms(train: pd.DataFrame) -> list[dict]:
    atoms: list[dict] = []
    for f in ("klass", "family", "observable", "event_type", "p_side", "model", "sector"):
        for v, n in train[f].astype(str).value_counts().items():
            if n >= MIN_SUPPORT_ROWS and v not in ("None", "unknown", "nan"):
                atoms.append({"field": f, "op": "eq", "value": v})
    for f in ("horizon_days", "vol_q", "mom_q", "liq_q"):
        vals = sorted(train[f].dropna().unique())
        for v in vals:
            atoms.append({"field": f, "op": "eq", "value": float(v)})
        for v in vals[1:-1]:
            atoms.append({"field": f, "op": "gte", "value": float(v)})
            atoms.append({"field": f, "op": "lte", "value": float(v)})
    for v in (0.1, 0.2, 0.3):
        atoms.append({"field": "p_extremity", "op": "gte", "value": v})
    for v in (0.05, 0.1):
        atoms.append({"field": "p_extremity", "op": "lte", "value": v})
    return atoms


def _actions() -> list[dict]:
    return ([{"type": "abstain"}] + [{"type": "shrink", "lambda": x} for x in SHRINK_GRID]
            + [{"type": "reweight", "factor": x} for x in REWEIGHT_GRID])


def _supported(m: np.ndarray, days: np.ndarray) -> bool:
    return int(m.sum()) >= MIN_SUPPORT_ROWS and len(set(days[m])) >= MIN_SUPPORT_DAYS


def greedy_rules(train: pd.DataFrame, b_row: np.ndarray, n_rules: int, *,
                 max_pairs: int = 60) -> tuple[list[dict], dict]:
    """Forward-stagewise search on TRAIN Brier over the same schema the model
    writes in. Single atoms, then pairs of the best single atoms."""
    Q = questions_of(train, b_row)
    days = train["made_day"].to_numpy()
    atoms = _atoms(train)
    masks = {i: rule_mask({"when": [a]}, train) for i, a in enumerate(atoms)}
    atom_ids = [i for i, m in masks.items() if _supported(m, days)]
    acts = _actions()
    # rank single atoms by their best single-rule improvement, to seed pairs
    base_b = brier(score_rules(train, Q, b_row, []), Q.y)
    single = []
    for i in atom_ids:
        best = min(brier(score_rules(train, Q, b_row,
                                     [{"when": [atoms[i]], "action": a}]), Q.y) for a in acts)
        single.append((best, i))
    single.sort()
    top = [i for _, i in single[:12]]
    cands: list[list[dict]] = [[atoms[i]] for i in atom_ids]
    for x in range(len(top)):
        for y_ in range(x + 1, len(top)):
            a1, a2 = atoms[top[x]], atoms[top[y_]]
            if a1["field"] == a2["field"]:
                continue
            m = masks[top[x]] & masks[top[y_]]
            if _supported(m, days):
                cands.append([a1, a2])
            if len(cands) > len(atom_ids) + max_pairs:
                break
    chosen: list[dict] = []
    tried = 0
    cur = base_b
    for _ in range(n_rules):
        best, best_rule = cur, None
        used = [json.dumps(r["when"], sort_keys=True) for r in chosen]
        for when in cands:
            if json.dumps(when, sort_keys=True) in used:
                continue      # one rule per condition set: no stacking the same reweight
            for a in acts:
                r = {"when": when, "action": a}
                tried += 1
                s = brier(score_rules(train, Q, b_row, chosen + [r]), Q.y)
                if s < best - 1e-9:
                    best, best_rule = s, r
        if best_rule is None:
            break
        best_rule = {**best_rule, "rule_text": f"greedy step {len(chosen) + 1}: "
                     f"train Brier {cur:.5f} -> {best:.5f}"}
        chosen.append(best_rule)
        cur = best
    return chosen, {"n_atoms": len(atoms), "n_supported_atoms": len(atom_ids),
                    "n_candidate_conditions": len(cands), "n_rule_evaluations": tried,
                    "train_brier_no_rules": base_b, "train_brier_final": cur}


def random_rules(train: pd.DataFrame, n_rules: int, rng: np.random.Generator) -> list[dict]:
    """Same schema, same count. Conditions are SUPPORTED atoms on DISTINCT
    fields, and a two-condition combination must itself pass the support bar a
    greedy rule passes (redrawn otherwise): the control never fires on nothing."""
    days = train["made_day"].to_numpy()
    atoms = [a for a in _atoms(train) if _supported(rule_mask({"when": [a]}, train), days)]
    acts = _actions()
    out = []
    for k in range(n_rules):
        when = [atoms[int(rng.integers(len(atoms)))]]
        if int(rng.integers(1, 3)) == 2:
            for _ in range(50):
                other = atoms[int(rng.integers(len(atoms)))]
                if other["field"] == when[0]["field"]:
                    continue
                if _supported(rule_mask({"when": when + [other]}, train), days):
                    when = when + [other]
                    break
        out.append({"when": when, "action": acts[int(rng.integers(len(acts)))],
                    "rule_text": f"random control rule {k + 1}"})
    return out


# ==========================================================================
# 6. SELECT ON VALIDATION, REPORT ON HELD-OUT
# ==========================================================================
def select_on_validation(rules: Sequence[dict], val: pd.DataFrame, b_val: np.ndarray
                         ) -> tuple[list[dict], dict]:
    """Forward selection over FROZEN rules: add the rule that lowers validation
    Brier most; stop when none does."""
    Q = questions_of(val, b_val)
    chosen: list[dict] = []
    cur = brier(score_rules(val, Q, b_val, []), Q.y)
    start = cur
    remaining = list(rules)
    while remaining:
        scores = [(brier(score_rules(val, Q, b_val, chosen + [r]), Q.y), i)
                  for i, r in enumerate(remaining)]
        s, i = min(scores)
        if s >= cur - 1e-9:
            break
        chosen.append(remaining.pop(i))
        cur = s
    return chosen, {"validation_brier_no_rules": start, "validation_brier_selected": cur,
                    "n_offered": len(rules), "n_selected": len(chosen)}


def _block_bootstrap(d: np.ndarray, day: np.ndarray, rng: np.random.Generator,
                     n: int = BOOTSTRAP_DRAWS) -> tuple[float, float]:
    """95% interval of the mean per-question Brier change, resampling ISO WEEKS.

    Not days: an h=5 forecast made Monday and one made Tuesday on the same
    ticker share four of five return days, so day blocks are not independent
    and a day-block interval is too narrow (CLAUDE.md protocol 11).
    """
    day = _weeks(day)
    days = np.unique(day)
    if len(days) < 2:
        return float("nan"), float("nan")
    by = {k: d[day == k] for k in days}
    sums = np.array([by[k].sum() for k in days])
    cnts = np.array([len(by[k]) for k in days])
    stats = []
    for _ in range(n):
        idx = rng.integers(0, len(days), len(days))
        stats.append(sums[idx].sum() / max(cnts[idx].sum(), 1))
    return float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))


def _weeks(day: np.ndarray) -> np.ndarray:
    return pd.to_datetime(pd.Series(day)).dt.to_period("W").astype(str).to_numpy()


def evaluate(g: pd.DataFrame, b_row: np.ndarray, rules: Sequence[dict],
             rng: np.random.Generator, *, label: str) -> dict:
    """Held-out report for one rule set versus no rules."""
    from backend.services.forecast_reputation import _score
    Q = questions_of(g, b_row)
    p0 = score_rules(g, Q, b_row, [])
    p1 = score_rules(g, Q, b_row, rules)
    d = (p1 - Q.y) ** 2 - (p0 - Q.y) ** 2
    s0, s1 = _score(p0, Q.y), _score(p1, Q.y)
    lo, hi = _block_bootstrap(d, Q.day, rng)
    by_month = {}
    for m in sorted(set(Q.month)):
        k = Q.month == m
        by_month[m] = {"n_questions": int(k.sum()), "d_brier": float(d[k].mean()),
                       "share_of_total_change": (float(d[k].sum() / d.sum())
                                                 if abs(d.sum()) > 0 else None)}
    loo = {m: float(d[Q.month != m].mean()) for m in by_month if (Q.month != m).any()}
    wk = pd.to_datetime(pd.Series(Q.day)).dt.to_period("W").astype(str).to_numpy()
    by_week = {w_: {"n_questions": int((wk == w_).sum()), "d_brier": float(d[wk == w_].mean())}
               for w_ in sorted(set(wk))}
    nr = Q.klass != "review"
    non_review = {"n_questions": int(nr.sum()),
                  "d_brier": float(d[nr].mean()) if nr.any() else None,
                  "ci95_week_block": (list(_block_bootstrap(d[nr], Q.day[nr], rng))
                                     if nr.any() else None)}
    by_klass = {str(k): {"n_questions": int((Q.klass == k).sum()),
                         "d_brier": float(d[Q.klass == k].mean())}
                for k in sorted(set(Q.klass))}
    fired = np.zeros(len(g), bool)
    for r in rules:
        fired |= rule_mask(r, g)
    return {"label": label, "n_rules": len(rules), "n_rows": int(len(g)),
            "n_questions": int(len(Q.y)), "n_rows_fired": int(fired.sum()),
            "brier_no_rules": s0["brier"], "brier_rules": s1["brier"],
            "skill_no_rules": s0["skill"], "skill_rules": s1["skill"],
            "d_brier": float(d.mean()), "d_brier_ci95_week_block": [lo, hi],
            "n_day_blocks": int(len(np.unique(Q.day))),
            "n_week_blocks": int(len(np.unique(_weeks(Q.day)))),
            "by_month": by_month, "by_week": by_week,
            "weeks_negative": int(sum(v["d_brier"] < 0 for v in by_week.values())),
            "n_weeks": len(by_week), "non_review": non_review,
            "leave_one_month_out_d_brier": loo,
            "worst_loo_d_brier": (max(loo.values()) if loo else None),
            "by_klass": by_klass}


# ==========================================================================
# 7. "WRITES ITS OWN WEIGHTS": reputation weights fitted on train
# ==========================================================================
def weights_experiment(train: pd.DataFrame, held: pd.DataFrame, b_tr: np.ndarray,
                       b_ho: np.ndarray, rng: np.random.Generator) -> dict:
    """Family weights from `forecast_reputation.tune` + `weights` on TRAIN, frozen,
    then pooled on held-out; versus equal weights and investigator-only. Plus a
    per-(klass, observable) logistic recalibration fitted on train."""
    from backend.services import forecast_reputation as FR
    tr, ho = train, held          # arm = the specialist id, as the nightly refit keys it
    out: dict[str, Any] = {}
    tuned = FR.tune(tr[["arm", "p", "y", "made_at", "made_day", "horizon_days", "observable",
                        "ticker", "threshold", "benchmark"]].copy())
    out["tune"] = {k: tuned.get(k) for k in ("status", "unit", "n_folds", "identified",
                                              "best", "brier_climatology")}
    Q = questions_of(ho, b_ho)
    p_raw = ho["p"].to_numpy(float)
    variants: dict[str, np.ndarray] = {}
    variants["equal_weights"] = pooled(Q, np.ones(len(ho)), p_raw)
    variants["investigator_only"] = pooled(
        Q, (ho["klass"] == "investigator").to_numpy(float), p_raw)
    variants["climatology"] = Q.b.copy()
    if tuned.get("status") == "OK":
        best = tuned["best"]
        sk = FR.arm_skill(tr, split="date_half")
        w = FR.weights(sk, k_prior=best["k_prior"], gamma=best["gamma"],
                       floor=FR.DEFAULTS["floor"])
        out["fitted_weights"] = {str(k): round(float(v), 4) for k, v in w.items() if v > 0}
        wr = np.array([float(w.get(a, 0.0)) for a in ho["arm"]])
        from backend.services.forecast_reputation import _logit, _sigmoid
        lg = _logit(p_raw)
        n = len(Q.y)
        num = np.bincount(Q.qinv, weights=wr * lg, minlength=n)
        den = np.bincount(Q.qinv, weights=wr, minlength=n)
        has = den > 0
        agg = np.divide(num, den, out=np.zeros_like(num), where=has)
        variants["reputation_weights_fit_on_train"] = np.where(
            has, _sigmoid(float(best["kappa"]) * agg), Q.b)
    # per-cell logistic recalibration: y ~ sigmoid(a + c*logit p), ridge-shrunk
    cal = recalibration_fit(train)
    out["recalibration_cells"] = len(cal)
    variants["recalibrated_on_train"] = pooled(Q, np.ones(len(ho)), recalibrate(ho, cal))
    rep = {}
    base = variants["equal_weights"]
    for name, pq in variants.items():
        s = FR._score(pq, Q.y)
        d = (pq - Q.y) ** 2 - (base - Q.y) ** 2
        lo, hi = _block_bootstrap(d, Q.day, rng)
        by_month = {m: float(d[Q.month == m].mean()) for m in sorted(set(Q.month))}
        nr = Q.klass != "review"
        rep[name] = {"brier": s["brier"], "skill": s["skill"], "n_questions": int(len(Q.y)),
                     "d_brier_vs_equal": float(d.mean()), "ci95_week_block": [lo, hi],
                     "d_brier_vs_equal_by_month": by_month,
                     "by_klass": {str(k): float(d[Q.klass == k].mean())
                                  for k in sorted(set(Q.klass))},
                     "non_review_d_brier_vs_equal": (float(d[nr].mean()) if nr.any() else None),
                     "non_review_ci95": (list(_block_bootstrap(d[nr], Q.day[nr], rng))
                                         if nr.any() else None)}
    out["held_out"] = rep
    return out


def recalibration_fit(train: pd.DataFrame, *, min_n: int = 200, ridge: float = 5.0
                      ) -> dict:
    from backend.services.forecast_reputation import _logit
    cal = {}
    for (k, o), sub in train.groupby(["klass", "observable"]):
        if len(sub) < min_n:
            continue
        x = _logit(sub["p"].to_numpy(float))
        y = sub["y"].to_numpy(float)
        a, c = 0.0, 1.0
        for _ in range(50):   # Newton steps on a ridge-penalised logistic fit toward (0, 1)
            z = np.clip(a + c * x, -30, 30)
            q = 1 / (1 + np.exp(-z))
            ga = np.sum(q - y) + ridge * a
            gc = np.sum((q - y) * x) + ridge * (c - 1.0)
            wq = q * (1 - q)
            haa = np.sum(wq) + ridge
            hcc = np.sum(wq * x * x) + ridge
            hac = np.sum(wq * x)
            det = haa * hcc - hac * hac
            if det <= 0:
                break
            da = (hcc * ga - hac * gc) / det
            dc = (haa * gc - hac * ga) / det
            a, c = a - da, c - dc
            if abs(da) + abs(dc) < 1e-8:
                break
        cal[(str(k), str(o))] = (float(a), float(c))
    return cal


def recalibrate(g: pd.DataFrame, cal: dict) -> np.ndarray:
    from backend.services.forecast_reputation import _logit
    p = g["p"].to_numpy(float).copy()
    x = _logit(p)
    for i, (k, o) in enumerate(zip(g["klass"].astype(str), g["observable"].astype(str))):
        if (k, o) in cal:
            a, c = cal[(k, o)]
            p[i] = 1 / (1 + math.exp(-max(-30.0, min(30.0, a + c * x[i]))))
    return p


# ==========================================================================
# 8. THE RUN
# ==========================================================================
def field_values(train: pd.DataFrame) -> dict:
    return {f: sorted(train[f].astype(str).value_counts().loc[lambda s: s >= 30].index.tolist())[:40]
            for f in CATEGORICAL_FIELDS}


def run(rows: Sequence[dict], *, bars: pd.DataFrame | None, out_dir: Path,
        complete_fn: Callable[[str, str], dict] | None = None,
        n_rules: int = N_RULES_DEFAULT, t1: str = T1_DEFAULT, t2: str = T2_DEFAULT,
        ledger_label: str = "", frozen_llm: Sequence[dict] | None = None,
        frozen_meta: dict | None = None, allow_unbound_frozen: bool = False) -> dict:
    """The whole experiment. `complete_fn(system, user) -> {"text", "cost_usd", ...}`
    is injected; None runs greedy + random only and says so."""
    rng = np.random.default_rng(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)
    g = frame_from_rows(rows, sectors=sector_map())
    g = attach_bar_features(g, bars if bars is not None else pd.DataFrame())
    sp = split_frame(g, t1, t2)
    edges = fit_buckets(sp.train)
    tr, va, ho = (apply_buckets(x, edges) for x in (sp.train, sp.validation, sp.held_out))
    br = base_rates(tr)
    b_tr, b_va, b_ho = base_rate_for(tr, br), base_rate_for(va, br), base_rate_for(ho, br)
    run_contract = {**contract(), "t1": t1, "t2": t2, "n_rules": n_rules}
    receipt: dict[str, Any] = {
        "schema": SCHEMA, "contract": run_contract,
        "contract_hash": contract_hash(run_contract),
        "licence": "PRODUCT_EXPERIMENT", "ledger": ledger_label,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": sp.meta, "bucket_edges_train": edges,
        "feature_coverage": {c: float(g[c].notna().mean()) for c in ("vol63", "mom20", "dvol20")},
        "sector_coverage": float((g["sector"] != "unknown").mean()),
    }
    # ---- PROPOSE (train only) ----
    tables = train_tables(tr)
    assert_train_only(tables, t1)
    (out_dir / "train_tables.json").write_text(json.dumps(tables, indent=1, default=str),
                                               encoding="utf-8")
    sources: dict[str, list[dict]] = {}
    llm_meta: dict[str, Any] = {"called": False}
    if complete_fn is not None:
        prompt = llm_prompt(tables, n_rules, field_values(tr))
        llm_meta = {"called": True, "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:16],
                    "prompt_chars": len(prompt)}
        reply = complete_fn(LLM_SYSTEM, prompt)
        llm_meta.update({k: reply.get(k) for k in ("status", "model", "served_model",
                                                   "cost_usd", "tokens_in", "tokens_out",
                                                   "budget_charge_usd")})
        good, bad = parse_llm_rules(reply.get("text"))
        llm_meta.update({"n_valid": len(good), "refused": bad})
        (out_dir / "llm_reply.txt").write_text(str(reply.get("text")), encoding="utf-8")
        sources["llm"] = good
    elif frozen_llm is not None:
        # RE-SCORE, never re-write: rules frozen by an earlier run on THIS split.
        binding = "bound"
        if frozen_meta is None:
            if not allow_unbound_frozen:
                raise LabRefused("frozen rules carry no _meta (contract hash, t1, t2); "
                                 "refusing to re-score them on a split they may have seen")
            binding = "UNBOUND (legacy file; caller asserted the split)"
        else:
            want = {"t1": t1, "t2": t2, "contract_hash": contract_hash(run_contract)}
            got = {k: frozen_meta.get(k) for k in want}
            if got != want:
                raise LabRefused(f"frozen rules were frozen for {got}, this run is {want}")
        for r in frozen_llm:
            ok, why = validate_rule(r)
            if ok is None:
                raise LabRefused(f"frozen rule {r.get('rule_hash')} no longer validates: {why}")
        bad_hash = [r.get("rule_hash") for r in frozen_llm if rule_hash(r) != r.get("rule_hash")]
        if bad_hash:
            raise LabRefused(f"frozen rules altered since freezing: {bad_hash}")
        sources["llm"] = [{k: r[k] for k in ("when", "action", "rule_text")} for r in frozen_llm]
        llm_meta = {"called": False, "rescored_frozen": True, "binding": binding,
                    "n_valid": len(frozen_llm),
                    "frozen_hashes": [r["rule_hash"] for r in frozen_llm]}
    receipt["llm"] = llm_meta
    greedy, gmeta = greedy_rules(tr, b_tr, n_rules)
    sources["greedy"] = greedy
    receipt["greedy_search"] = gmeta
    sources["random"] = random_rules(tr, n_rules, rng)
    # ---- FREEZE ----
    frozen = {s: freeze(r, s) for s, r in sources.items()}
    meta = {"t1": t1, "t2": t2, "contract_hash": contract_hash(run_contract), "schema": SCHEMA}
    (out_dir / "frozen_rules.json").write_text(
        json.dumps({**frozen, "_meta": meta}, indent=1, default=str), encoding="utf-8")
    receipt["frozen_rules_sha"] = hashlib.sha256(
        (out_dir / "frozen_rules.json").read_bytes()).hexdigest()[:16]
    # ---- SELECT (validation) ----
    selected, sel_meta = {}, {}
    for s, rules in frozen.items():
        selected[s], sel_meta[s] = select_on_validation(rules, va, b_va)
    receipt["selection"] = sel_meta
    receipt["selected_rule_hashes"] = {s: [r["rule_hash"] for r in v] for s, v in selected.items()}
    # ---- REPORT (held-out, once) ----
    held: dict[str, Any] = {}
    for s in frozen:
        held[s] = {"all_frozen": evaluate(ho, b_ho, frozen[s], rng, label=f"{s}/all"),
                   "validation_selected": evaluate(ho, b_ho, selected[s], rng,
                                                   label=f"{s}/selected")}
    # the random control's DISTRIBUTION: many draws, each selected on validation
    dist_all, dist_sel = [], []
    for _ in range(RANDOM_CONTROL_DRAWS):
        rr = random_rules(tr, n_rules, rng)
        Qh = questions_of(ho, b_ho)
        y0 = brier(score_rules(ho, Qh, b_ho, []), Qh.y)
        dist_all.append(brier(score_rules(ho, Qh, b_ho, rr), Qh.y) - y0)
        sel, _ = select_on_validation(rr, va, b_va)
        dist_sel.append(brier(score_rules(ho, Qh, b_ho, sel), Qh.y) - y0)
    q = lambda xs: {k: float(np.quantile(xs, v)) for k, v in  # noqa: E731
                    (("p05", 0.05), ("p50", 0.5), ("p95", 0.95))}
    held["random_control_distribution"] = {"draws": RANDOM_CONTROL_DRAWS,
                                           "d_brier_all": q(dist_all),
                                           "d_brier_selected": q(dist_sel)}
    for s in frozen:
        v = held[s]["validation_selected"]["d_brier"]
        held[s]["selected_rank_vs_random_selected"] = float(np.mean(np.asarray(dist_sel) <= v))
    # paired: the SAME held-out questions under two selected rule sets
    Qh = questions_of(ho, b_ho)
    se = {s_: (score_rules(ho, Qh, b_ho, selected[s_]) - Qh.y) ** 2 for s_ in frozen}
    paired = {}
    for a_, b_ in (("llm", "greedy"), ("llm", "random"), ("greedy", "random")):
        if a_ in se and b_ in se:
            dd = se[a_] - se[b_]
            paired[f"{a_} - {b_}"] = {"d_brier": float(dd.mean()),
                                      "ci95_week_block": list(_block_bootstrap(dd, Qh.day, rng))}
    held["paired"] = paired
    held["held_out_reads"] = 2 if llm_meta.get("rescored_frozen") else 1
    receipt["held_out"] = held
    receipt["n_rules_tried_total"] = {
        "llm_valid": len(sources.get("llm", [])),
        "llm_refused": len(llm_meta.get("refused") or []),
        "greedy_rule_evaluations_on_train": gmeta["n_rule_evaluations"],
        "random_primary": len(sources["random"]),
        "random_control_draws_x_rules": RANDOM_CONTROL_DRAWS * n_rules}
    # ---- WEIGHTS ----
    receipt["weights"] = weights_experiment(tr, ho, b_tr, b_ho, rng)
    receipt["verdict"] = verdict(held, receipt["weights"])
    p = out_dir / "self_rule_lab_receipt.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)
    receipt["receipt_path"] = str(p)
    return receipt


def verdict(held: dict, weights: dict) -> dict:
    """Plain statements, computed -- never hand-written."""
    lines = []
    sel = {s: held[s]["validation_selected"] for s in ("llm", "greedy", "random") if s in held}
    rnd = held.get("random_control_distribution", {}).get("d_brier_selected", {})
    for s, v in sel.items():
        lo, hi = v["d_brier_ci95_week_block"]
        sign = ("lower (better)" if hi < 0 else "higher (worse)" if lo > 0
                else "not distinguishable from zero")
        nr = v.get("non_review") or {}
        nr_txt = (f"; ex-review {nr['d_brier']:+.5f} [{nr['ci95_week_block'][0]:+.5f}, "
                  f"{nr['ci95_week_block'][1]:+.5f}] n {nr['n_questions']}"
                  if nr.get("d_brier") is not None else "")
        lines.append(f"{s}: {v['n_rules']} selected rules, held-out d_Brier "
                     f"{v['d_brier']:+.5f} [{lo:+.5f}, {hi:+.5f}] over {v['n_questions']} "
                     f"questions / {v['n_day_blocks']} days / {v['n_week_blocks']} week "
                     f"blocks, {v['weeks_negative']}/"
                     f"{v['n_weeks']} weeks lower: {sign}{nr_txt}")
    for pair, v in (held.get("paired") or {}).items():
        lo, hi = v["ci95_week_block"]
        word = ("first lower" if hi < 0 else "second lower" if lo > 0
                else "not distinguishable")
        lines.append(f"{pair} (held-out, selected sets, paired): {v['d_brier']:+.5f} "
                     f"[{lo:+.5f}, {hi:+.5f}] -> {word}")
    if rnd:
        lines.append(f"random control (selected, {held['random_control_distribution']['draws']} "
                     f"draws): p05 {rnd['p05']:+.5f} p50 {rnd['p50']:+.5f} p95 {rnd['p95']:+.5f}")
    for name, v in (weights.get("held_out") or {}).items():
        lo, hi = v["ci95_week_block"]
        lines.append(f"weights/{name}: Brier {v['brier']:.5f} skill {v['skill']:+.4f}, "
                     f"vs equal {v['d_brier_vs_equal']:+.5f} [{lo:+.5f}, {hi:+.5f}]")
    reads = held.get("held_out_reads", 1)
    return {"lines": lines,
            "claim": (f"none: PRODUCT_EXPERIMENT observation; held-out read {reads} time(s)"
                      + (" -- a RE-SCORE of rules whose held-out was already read once"
                         if reads > 1 else ""))}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", required=True, help="a READ-ONLY snapshot of predictions.jsonl")
    ap.add_argument("--bars", action="append", default=[], help="bars parquet(s)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--llm", action="store_true", help="call DeepSeek through the guarded path")
    ap.add_argument("--n-rules", type=int, default=N_RULES_DEFAULT)
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--t1", default=T1_DEFAULT)
    ap.add_argument("--t2", default=T2_DEFAULT)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--frozen", default=None,
                    help="re-score the 'llm' rules of an earlier frozen_rules.json (no model call)")
    ap.add_argument("--frozen-unbound", action="store_true",
                    help="accept a legacy frozen file with no _meta; the receipt says UNBOUND")
    a = ap.parse_args(argv)
    from backend.services import forecast_reputation as FR
    rows = FR.load_ledger(a.ledger)
    bars = pd.concat([pd.read_parquet(b, columns=["symbol", "date", "close", "volume"])
                      for b in a.bars], ignore_index=True) if a.bars else None
    fn = None
    if a.llm:
        from backend.services import llm_analyzer as LA

        def fn(system: str, user: str) -> dict:
            return LA.call_named("deepseek", system, user, purpose="self_rule_lab",
                                 max_tokens=a.max_tokens, temperature=a.temperature,
                                 validate=lambda t: parse_llm_rules(t)[0] != [])
    ff = json.loads(Path(a.frozen).read_text(encoding="utf-8")) if a.frozen else {}
    rec = run(rows, bars=bars, out_dir=Path(a.out), complete_fn=fn, n_rules=a.n_rules,
              t1=a.t1, t2=a.t2, ledger_label=str(a.ledger), frozen_llm=ff.get("llm"),
              frozen_meta=ff.get("_meta"), allow_unbound_frozen=a.frozen_unbound)
    print("\n".join(rec["verdict"]["lines"]))
    print(f"receipt: {rec['receipt_path']}")
    if a.llm and not rec["llm"].get("n_valid"):
        print(f"LLM PROPOSE FAILED: {rec['llm']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
