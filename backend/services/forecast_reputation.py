"""The reputation layer: which forecaster to believe, and by how much.

WHY THIS EXISTS
===============
`NEGATIVE_RESULTS.md` §64 graded the frozen forecast ledger and found it splits
in two: the `investigator:*` arms (a *process* -- gather evidence, name sources,
state the falsifier) beat climatology held out, and nine thematic personas have
NEGATIVE discrimination -- their optimal weight, held out, is zero. Anything that
averages the bench without knowing that injects anti-signal.

This module is pure arithmetic over `predictions.jsonl` (no LLM, no network):

    arm_skill          held-out Brier skill per arm (later half by date)
    weights            s_shr = n/(n+k) * skill ; w = clip(s_shr, floor, 1)**gamma ; normalised
    pool               sigmoid(kappa * sum_i w_i logit(p_i))   over the arms present
    calibration_curve  investigator:* at h, by year: bin of p -> realised rate / return
    restricted_check   Profit-Mirage: skill on rows made on/after a cut, beside the full
    refit              tunes k_prior / gamma / kappa by leave-one-quarter-out and writes
                       <OPTIMUS_LEDGER_DIR>/reputation/reputation_<date>.json

The formula set is `docs/research_notes/2026-09-25/research_llm_engine.md` Q3.
The floor is the load-bearing part: the crowd-wisdom literature assumes the
worst forecaster is noise; this ledger holds forecasters worse than noise.

CONVENTIONS THAT MAKE THE NUMBERS AGREE WITH §64
================================================
* **Held out = the later half of an arm's rows in date order**, not a date
  boundary. The nine thematic arms were all written inside four minutes on
  2026-08-12; a date-boundary split would leave their test half empty. Rows
  are sorted stably by `made_at` (falling back to `resolves_after`, then
  `resolved_at`) and the last `n - n//2` are scored.
* **Climatology is the base rate of the scored rows** -- the scoreboard's
  convention. It is the harder baseline to beat (in-sample base rate).
* **Discrimination** = mean p on outcomes that happened minus mean p on those
  that did not (the scoreboard's definition).

WHAT IS TUNED AND WHERE IT LIVES
================================
`refit` tunes the three constants on the real ledger and writes them INTO THE
RECEIPT, not into `config.py`, until two consecutive refits agree (the receipt
records whether the previous one does). A quarter is the preferred CV unit; a
ledger that lies inside one quarter (the live one, in 2026-09) falls back to
leave-one-DAY-out and the receipt names the unit it actually used.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Used by readers (the scoreboard) before any refit receipt exists. Not tuned.
DEFAULTS: dict[str, float] = {"k_prior": 500.0, "gamma": 2.0, "kappa": 1.0,
                              "floor": 0.0}

#: The search space. kappa < 1 is allowed on purpose: §64 found the investigator
#: arms OVERconfident (best shrink 0.65 toward base), so un-extremizing is a live
#: answer and forbidding it would bias the tune toward confident wrongness.
GRID: dict[str, tuple[float, ...]] = {
    "k_prior": (0.0, 100.0, 300.0, 1000.0, 3000.0),
    "gamma": (1.0, 2.0, 3.0, 4.0),
    "kappa": (0.25, 0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 2.0),
}

#: Profit-Mirage cut: the first day the forward ledger was written.
RESTRICT_SINCE = "2026-08-11"

#: Probabilities are clipped before logit; a stated 0 or 1 is not infinite evidence.
P_CLIP = 1e-3

DATE_COLS: tuple[str, ...] = ("made_at", "resolves_after", "resolved_at")
QUESTION_COLS: tuple[str, ...] = ("ticker", "observable", "horizon_days",
                                  "threshold", "benchmark", "made_day")


# ── loading ──────────────────────────────────────────────────────────────────
def _outcome01(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v) if v in (0, 1) else None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "hit", "1", "resolved_true"):
            return 1.0
        if s in ("false", "no", "miss", "0", "resolved_false"):
            return 0.0
    return None


def _num(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return f


def graded_frame_from_rows(rows: Iterable[dict]) -> pd.DataFrame:
    """Ledger records -> one row per graded forecast.

    Columns: arm, p, y, made_at (UTC ts), made_day, horizon_days, observable,
    ticker, threshold, benchmark, ret, rel_ret. Ungraded rows and probabilities
    outside [0, 1] are dropped (they are not scorable, not zero).
    """
    out = []
    for r in rows:
        y = _outcome01(r.get("outcome"))
        p = _num(r.get("probability"))
        if y is None or not (0.0 <= p <= 1.0):
            continue
        det = r.get("resolution_detail") or {}
        if not isinstance(det, dict):
            det = {}
        rel = det.get("vs_benchmark", r.get("vs_benchmark"))
        out.append({
            "arm": str(r.get("specialist")), "p": p, "y": y,
            "made_at": r.get("made_at"), "resolves_after": r.get("resolves_after"),
            "horizon_days": r.get("horizon_days"), "observable": r.get("observable"),
            "ticker": r.get("ticker"), "threshold": str(r.get("threshold")),
            "benchmark": str(r.get("benchmark")),
            "ret": _num(det.get("realised_return")), "rel_ret": _num(rel),
        })
    g = pd.DataFrame(out, columns=["arm", "p", "y", "made_at", "resolves_after",
                                   "horizon_days", "observable", "ticker",
                                   "threshold", "benchmark", "ret", "rel_ret"])
    g["made_at"] = pd.to_datetime(g["made_at"], utc=True, errors="coerce",
                                  format="ISO8601")
    g["made_day"] = g["made_at"].dt.strftime("%Y-%m-%d")
    return g


def load_ledger(path: Path | str | None = None) -> list[dict]:
    """Read-only. Unparseable lines are skipped and counted in the log."""
    if path is None:
        from backend import config as _config
        path = Path(_config.OPTIMUS_LEDGER_DIR) / "predictions.jsonl"
    rows, bad = [], 0
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    if bad:
        logger.warning("forecast_reputation: %d unparseable ledger lines skipped", bad)
    return rows


# ── scoring ──────────────────────────────────────────────────────────────────
def _date_col(df: pd.DataFrame, date_col: str | None) -> str:
    if date_col:
        if date_col not in df.columns:
            raise ValueError(f"date column {date_col!r} not in frame")
        return date_col
    for c in DATE_COLS:
        if c in df.columns:
            return c
    raise ValueError(f"arm_skill needs one of {DATE_COLS} to split by date")


def _score(p: np.ndarray, y: np.ndarray) -> dict:
    n = len(y)
    if n == 0:
        return {"n": 0, "brier": np.nan, "clim": np.nan, "skill": np.nan,
                "disc": np.nan, "base_rate": np.nan, "calib_gap": np.nan}
    base = float(y.mean())
    brier = float(np.mean((p - y) ** 2))
    clim = float(np.mean((base - y) ** 2))
    skill = (1.0 - brier / clim) if clim > 0 else np.nan
    win, loss = p[y == 1], p[y == 0]
    disc = float(win.mean() - loss.mean()) if len(win) and len(loss) else np.nan
    return {"n": n, "brier": brier, "clim": clim, "skill": skill, "disc": disc,
            "base_rate": base, "calib_gap": float(p.mean() - base)}


def arm_skill(graded: pd.DataFrame, *, arm_col: str = "arm", p_col: str = "p",
              y_col: str = "y", split: str = "date_half",
              date_col: str | None = None) -> pd.DataFrame:
    """Per-arm Brier skill vs climatology, on the LATER half by date.

    `split="date_half"` scores the last n - n//2 rows of each arm in date order;
    `split="none"` scores every row (used inside CV folds, where the fold is
    already the hold-out). Index = arm; columns n, brier, clim, skill, disc,
    base_rate, calib_gap, n_total, test_from, test_to.
    """
    if split not in ("date_half", "none"):
        raise ValueError(f"unknown split {split!r}")
    cols = ["n", "brier", "clim", "skill", "disc", "base_rate", "calib_gap",
            "n_total", "test_from", "test_to"]
    if graded.empty:
        return pd.DataFrame(columns=cols)
    dc = _date_col(graded, date_col)
    recs = {}
    for arm, sub in graded.groupby(arm_col, sort=True):
        sub = sub.assign(_t=pd.to_datetime(sub[dc], utc=True, errors="coerce",
                                           format="ISO8601"))
        sub = sub.sort_values("_t", kind="stable")
        n_total = len(sub)
        test = sub.iloc[n_total // 2:] if split == "date_half" else sub
        s = _score(test[p_col].to_numpy(float), test[y_col].to_numpy(float))
        s["n_total"] = n_total
        s["test_from"] = test["_t"].min() if len(test) else pd.NaT
        s["test_to"] = test["_t"].max() if len(test) else pd.NaT
        recs[arm] = s
    return pd.DataFrame.from_dict(recs, orient="index")[cols]


def weights(skill: pd.DataFrame, *, k_prior: float, gamma: float,
            floor: float = 0.0) -> pd.Series:
    """s_shr = n/(n+k) * skill; w = clip(s_shr, floor, 1) ** gamma; normalised.

    A NaN skill (an arm with no scorable hold-out) gets weight 0. If no arm has
    positive weight the result is all zeros -- NOT a uniform average, which
    would hand the anti-signal arms a vote.
    """
    n = skill["n"].astype(float).to_numpy()
    s = skill["skill"].astype(float).to_numpy()
    s = np.where(np.isfinite(s), s, 0.0)
    shr = np.divide(n, n + k_prior, out=np.zeros_like(n), where=(n + k_prior) > 0) * s
    w = np.clip(shr, floor, 1.0) ** gamma
    tot = float(w.sum())
    w = w / tot if tot > 0 else np.zeros_like(w)
    return pd.Series(w, index=skill.index, name="weight")


def _logit(p: np.ndarray | float) -> np.ndarray | float:
    p = np.clip(p, P_CLIP, 1 - P_CLIP)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def pool(ps: dict[str, float], w: pd.Series, *, kappa: float) -> float | None:
    """sigmoid(kappa * sum_i w_i logit(p_i)), weights renormalised over the arms
    PRESENT in `ps`. Returns None when no present arm carries weight -- the
    caller falls back to the base rate; 0.5 would be an invented forecast.
    """
    num, den = 0.0, 0.0
    for arm, p in ps.items():
        wi = float(w.get(arm, 0.0)) if arm in w.index else 0.0
        if wi <= 0 or p is None or not np.isfinite(p):
            continue
        num += wi * float(_logit(float(p)))
        den += wi
    if den <= 0:
        return None
    return float(_sigmoid(kappa * num / den))


# ── calibration ──────────────────────────────────────────────────────────────
def calibration_curve(graded: pd.DataFrame, *, arm_prefix: str = "investigator:",
                      horizon: int, n_bins: int = 10) -> pd.DataFrame:
    """Bin of stated p -> realised base rate and realised return, by year.

    Bins are p-deciles within each (year, observable); the ledger states
    discrete probabilities (0.25, 0.50, ...), so tied deciles are MERGED
    (`duplicates="drop"`) rather than split arbitrarily -- fewer than ten bins
    is the honest shape. Observables are kept apart: an `abs_move_exceeds`
    base rate and a `return_sign` base rate are different questions.
    `rel_ret_mean` is the realised return vs benchmark where the outcome row
    carries one (beats_benchmark), else NaN.
    """
    cols = ["arm_prefix", "horizon", "year", "observable", "bin", "n", "p_mean",
            "p_lo", "p_hi", "base_rate", "ret_mean", "rel_ret_mean", "n_rel"]
    g = graded[graded["arm"].astype(str).str.startswith(arm_prefix)
               & (pd.to_numeric(graded["horizon_days"], errors="coerce") == horizon)]
    if g.empty:
        return pd.DataFrame(columns=cols)
    g = g.assign(year=pd.to_datetime(g["made_at"], utc=True, errors="coerce",
                                     format="ISO8601").dt.year)
    out = []
    for (yr, obs), sub in g.groupby(["year", "observable"], sort=True):
        k = min(n_bins, len(sub))
        if k < 2:
            continue
        bins = pd.qcut(sub["p"], k, labels=False, duplicates="drop")
        for b, bb in sub.groupby(bins, sort=True):
            out.append({"arm_prefix": arm_prefix, "horizon": horizon,
                        "year": int(yr), "observable": obs, "bin": int(b),
                        "n": int(len(bb)), "p_mean": float(bb["p"].mean()),
                        "p_lo": float(bb["p"].min()), "p_hi": float(bb["p"].max()),
                        "base_rate": float(bb["y"].mean()),
                        "ret_mean": float(bb["ret"].mean()),
                        "rel_ret_mean": float(bb["rel_ret"].mean()),
                        "n_rel": int(bb["rel_ret"].notna().sum())})
    return pd.DataFrame(out, columns=cols)


# ── Profit-Mirage restricted check ───────────────────────────────────────────
def _family(arm: str) -> str:
    return "investigator" if arm.startswith("investigator:") else arm.split(":")[0]


def restricted_check(graded: pd.DataFrame, *, since: str = RESTRICT_SINCE) -> dict:
    """Held-out skill on rows made on/after `since`, printed beside the full.

    Every forecast in the ledger resolves after it was made, so a row made on or
    after the model's stated cutoff cannot have its outcome in the weights. If
    the cut excludes nothing, the receipt says so: the check then restates the
    full number rather than testing anything new.
    """
    cut = pd.Timestamp(since, tz="UTC")
    r = graded[graded["made_at"] >= cut]
    full, rest = arm_skill(graded), arm_skill(r)
    by_arm = []
    for arm in full.index:
        by_arm.append({"arm": arm, "n_full": int(full.loc[arm, "n"]),
                       "skill_full": _f(full.loc[arm, "skill"]),
                       "n_restricted": int(rest.loc[arm, "n"]) if arm in rest.index else 0,
                       "skill_restricted": _f(rest.loc[arm, "skill"]) if arm in rest.index else None})
    fam = {}
    for name, sub in graded.groupby(graded["arm"].map(_family)):
        rs = sub[sub["made_at"] >= cut]
        fam[name] = {"skill_full": _f(_pooled_heldout_skill(sub)),
                     "skill_restricted": _f(_pooled_heldout_skill(rs)),
                     "n_full": int(len(sub)), "n_restricted": int(len(rs))}
    return {"since": since, "n_rows_full": int(len(graded)),
            "n_rows_restricted": int(len(r)),
            "n_rows_excluded": int(len(graded) - len(r)),
            "restriction_binds": bool(len(r) < len(graded)),
            "by_family": fam, "by_arm": by_arm}


def _pooled_heldout_skill(sub: pd.DataFrame) -> float:
    """Family skill: each arm's later half, pooled, scored against the pooled base rate."""
    if sub.empty:
        return float("nan")
    parts = []
    for _, a in sub.groupby("arm"):
        a = a.sort_values("made_at", kind="stable")
        parts.append(a.iloc[len(a) // 2:])
    t = pd.concat(parts)
    return _score(t["p"].to_numpy(float), t["y"].to_numpy(float))["skill"]


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ── tuning ───────────────────────────────────────────────────────────────────
def _cv_units(g: pd.DataFrame) -> tuple[str, pd.Series]:
    q = g["made_at"].dt.tz_localize(None).dt.to_period("Q").astype(str)
    if q.nunique() >= 2:
        return "quarter", q
    return "day", g["made_day"]


def tune(g: pd.DataFrame, grid: dict[str, tuple[float, ...]] | None = None) -> dict:
    """Leave-one-unit-out over (k_prior, gamma, kappa), scored on pooled Brier.

    For each held-out unit: arm skill from the OTHER units (all their rows),
    weights, then every question (ticker, observable, horizon, threshold,
    benchmark, day) in the held-out unit is pooled across the arms that
    answered it. A question no weighted arm answered gets the training base
    rate for its (observable, horizon) -- identical for every candidate, so it
    cannot move the choice. Ties go to the simplest setting (kappa nearest 1,
    then smallest gamma, then smallest k).
    """
    grid = grid or GRID
    unit_name, units = _cv_units(g)
    g = g.assign(_u=units.values)
    g = g.assign(_q=g.groupby(list(QUESTION_COLS), dropna=False, sort=False).ngroup())
    uniq = sorted(g["_u"].dropna().unique())
    combos = [(k, ga) for k in grid["k_prior"] for ga in grid["gamma"]]
    kappas = np.asarray(grid["kappa"], float)
    se = {(k, ga, ka): 0.0 for k, ga in combos for ka in kappas}
    se_clim, n_q = 0.0, 0
    folds = []
    for u in uniq:
        tr, te = g[g["_u"] != u], g[g["_u"] == u]
        if tr.empty or te.empty:
            continue
        sk = arm_skill(tr, split="none")
        base = tr.groupby(["observable", "horizon_days"])["y"].mean()
        glob = float(tr["y"].mean())
        qid, qinv = np.unique(te["_q"].to_numpy(), return_inverse=True)
        yq = np.zeros(len(qid))
        np.maximum.at(yq, qinv, te["y"].to_numpy(float))  # outcome is per question
        first = te.groupby("_q", sort=True).first()
        bq = np.array([float(base.get((o, h), glob)) for o, h in
                       zip(first["observable"], first["horizon_days"])])
        lg = _logit(te["p"].to_numpy(float))
        arms = te["arm"].to_numpy()
        se_clim += float(np.sum((bq - yq) ** 2))
        n_q += len(qid)
        folds.append({"unit": str(u), "n_rows": int(len(te)), "n_questions": int(len(qid))})
        for k, ga in combos:
            w = weights(sk, k_prior=k, gamma=ga)
            wr = np.array([float(w.get(a, 0.0)) for a in arms])
            num = np.bincount(qinv, weights=wr * lg, minlength=len(qid))
            den = np.bincount(qinv, weights=wr, minlength=len(qid))
            has = den > 0
            agg = np.divide(num, den, out=np.zeros_like(num), where=has)
            for ka in kappas:
                pq = np.where(has, _sigmoid(ka * agg), bq)
                se[(k, ga, ka)] += float(np.sum((pq - yq) ** 2))
    if n_q == 0:
        return {"status": "REFUSED", "reason": "fewer than two CV units with data",
                "unit": unit_name, "n_folds": len(folds)}
    table = sorted(({"k_prior": k, "gamma": ga, "kappa": float(ka),
                     "brier": v / n_q, "skill": 1.0 - (v / n_q) / (se_clim / n_q)}
                    for (k, ga, ka), v in se.items()),
                   key=lambda r: (round(r["brier"], 10), abs(r["kappa"] - 1.0),
                                  r["gamma"],
                                  abs(math.log1p(r["k_prior"]) - math.log1p(DEFAULTS["k_prior"]))))
    best = table[0]
    # A constant is IDENTIFIED only if moving it (others held at best) changes
    # the CV Brier. When every arm that carries weight has the same n, k_prior
    # cancels in the normalisation and the tie-break -- not the data -- picks it.
    identified = {}
    for c in ("k_prior", "gamma", "kappa"):
        prof = [r["brier"] for r in table
                if all(r[o] == best[o] for o in ("k_prior", "gamma", "kappa") if o != c)]
        identified[c] = bool(max(prof) - min(prof) > 1e-9)
    return {"status": "OK", "unit": unit_name, "n_folds": len(folds),
            "identified": identified,
            "folds": folds, "n_questions": n_q,
            "brier_climatology": se_clim / n_q,
            "best": best, "top10": table[:10],
            "worst": table[-1]}


# ── refit ────────────────────────────────────────────────────────────────────
def _out_dir(out_dir: Path | str | None) -> Path:
    if out_dir is not None:
        return Path(out_dir)
    from backend import config as _config
    return Path(_config.OPTIMUS_LEDGER_DIR) / "reputation"


def _previous(out: Path, today: str) -> dict | None:
    prev = sorted(p for p in out.glob("reputation_*.json")
                  if p.stem.replace("reputation_", "") < today)
    for p in reversed(prev):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("status") == "OK" and d.get("tuned"):
            return d
    return None


def latest_constants(out_dir: Path | str | None = None) -> tuple[dict, str]:
    """Tuned constants from the newest OK receipt, else DEFAULTS. Returns (constants, source)."""
    out = _out_dir(out_dir)
    if out.exists():
        d = _previous(out, "9999-99-99")
        if d:
            t = d["tuned"]
            return ({"k_prior": t["k_prior"], "gamma": t["gamma"],
                     "kappa": t["kappa"], "floor": t.get("floor", 0.0)},
                    f"reputation_{d.get('date')}.json")
    return dict(DEFAULTS), "DEFAULTS (no refit receipt yet)"


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: (_f(v) if isinstance(v, (float, np.floating)) else
                 (int(v) if isinstance(v, (np.integer,)) else v))
             for k, v in r.items()} for r in df.to_dict(orient="records")]


def refit(ledger_path: Path | str | None = None, *, today: str | None = None,
          out_dir: Path | str | None = None,
          grid: dict[str, tuple[float, ...]] | None = None) -> dict:
    """Grade -> held-out arm skill -> tuned weights -> receipt. Read-only on the ledger.

    Writes `<out_dir>/reputation_<today>.json` (and `calibration_<today>.json`)
    whether it succeeds or refuses: a refusal is a finding, and a missing
    receipt is indistinguishable from a step that never ran.
    """
    today = today or date.today().isoformat()
    out = _out_dir(out_dir)
    rows = load_ledger(ledger_path)
    g = graded_frame_from_rows(rows)
    rec: dict[str, Any] = {
        "receipt": "forecast_reputation", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "date": today,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ledger": str(ledger_path) if ledger_path else "OPTIMUS_LEDGER_DIR/predictions.jsonl",
        "n_ledger": len(rows), "n_graded": int(len(g)),
        "made_at_range": [str(g["made_at"].min())[:10], str(g["made_at"].max())[:10]]
        if len(g) else None,
        "formula": ("s_shr = n/(n+k_prior)*skill ; w = clip(s_shr, floor, 1)**gamma, "
                    "normalised ; p = sigmoid(kappa * sum w_i logit p_i) over present arms"),
        "split": "per arm, later half of rows in made_at order (held out); "
                 "climatology = base rate of the scored rows",
    }
    path = out / f"reputation_{today}.json"
    if len(g) == 0 or g["arm"].nunique() == 0:
        rec.update({"status": "REFUSED",
                    "reason": "no graded forecasts -- run forecast_grader.grade_due() first"})
        _write_json(path, rec)
        return rec

    tuned = tune(g, grid)
    rec["cv"] = {k: tuned.get(k) for k in ("status", "unit", "n_folds", "folds", "identified",
                                           "n_questions", "brier_climatology",
                                           "top10", "worst", "reason")}
    if tuned["status"] != "OK":
        rec.update({"status": "REFUSED", "reason": f"tuning: {tuned.get('reason')}"})
        _write_json(path, rec)
        return rec
    b = tuned["best"]
    rec["tuned"] = {"k_prior": b["k_prior"], "gamma": b["gamma"], "kappa": b["kappa"],
                    "floor": DEFAULTS["floor"], "cv_brier": b["brier"],
                    "identified": tuned["identified"],
                    "cv_skill_vs_climatology": b["skill"],
                    "where": "receipt only -- NOT config, until two refits agree"}

    sk = arm_skill(g)
    w = weights(sk, k_prior=b["k_prior"], gamma=b["gamma"], floor=DEFAULTS["floor"])
    arms = []
    for arm in sk.index:
        r = sk.loc[arm]
        arms.append({"arm": arm, "family": _family(arm), "n": int(r["n"]),
                     "n_total": int(r["n_total"]), "brier": _f(r["brier"]),
                     "clim": _f(r["clim"]), "skill": _f(r["skill"]),
                     "disc": _f(r["disc"]), "calib_gap": _f(r["calib_gap"]),
                     "weight": float(w[arm])})
    rec["arms"] = sorted(arms, key=lambda a: (-a["weight"], -(a["skill"] or -9)))

    cal = {f"h{h}": _records(calibration_curve(g, horizon=h)) for h in (1, 5)}
    rec["calibration"] = cal
    rec["restricted_check"] = restricted_check(g)

    prev = _previous(out, today)
    if prev:
        pt = prev["tuned"]
        agrees = all(float(pt[k]) == float(rec["tuned"][k])
                     for k in ("k_prior", "gamma", "kappa"))
        rec["previous"] = {"date": prev.get("date"),
                           "tuned": {k: pt[k] for k in ("k_prior", "gamma", "kappa")},
                           "agrees": agrees}
    else:
        rec["previous"] = None
    rec["status"] = "OK"
    _write_json(out / f"calibration_{today}.json",
                {"receipt": "investigator_calibration", "date": today,
                 "arm_prefix": "investigator:", **cal})
    _write_json(path, rec)
    return rec


def format_table(rec: dict) -> str:
    """The per-arm table as text (the scoreboard prints this)."""
    lines = [f"{'arm':<28}{'n test':>8}{'skill':>9}{'disc':>8}{'weight':>9}"]
    for a in rec.get("arms", []):
        sk = "n/a" if a["skill"] is None else f"{a['skill'] * 100:.2f}%"
        dc = "n/a" if a["disc"] is None else f"{a['disc'] * 100:+.1f}"
        lines.append(f"{a['arm']:<28}{a['n']:>8,}{sk:>9}{dc:>8}{a['weight']:>9.3f}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - attended CLI
    r = refit()
    print(json.dumps({k: r.get(k) for k in ("status", "n_graded", "tuned", "reason")},
                     indent=1, default=str))
    print(format_table(r))
