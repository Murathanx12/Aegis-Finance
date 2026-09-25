"""The expected-return layer: one number per name, decomposed by component.

WHY THIS EXISTS (roadmap 2026-09-25 chunk 2; adjudication rows 2 and 5)
======================================================================
The best new intelligence sat BESIDE the ranker instead of inside the decision.
This module turns every signal the engine already has into one
`E[r_h]` -- expected return relative to the universe median at h sessions --
per candidate and date, and keeps each component a separate column so a later
autopsy can say which component was wrong.

    E[r_h] = regime_scale * sum_c  w_{c,h} * x_{c,h}        over AWAKE components
    phi_c  = regime_scale * w_c * (x_c - mean_c)             (Linear SHAP; exact)
    sum_c phi_c + baseline == E[r_h]                          asserted on every row

Components (`COMPONENTS`), each in expected-relative-return units:

* ``ranker``            `ranking.json` decile -> realised OOS net relative return (h=21 only)
* ``revision_flow``     `net_raises x n_firms` (>=3 firms) -> the sweep's measured top-k table
* ``investigator_dir``  investigator:* ``beats_benchmark`` p -> calibrated realised relative return
* ``thesis_card``       thesis_card:v1 p -> its own calibration once >=30 graded; asleep before
* ``catalyst``          a dated PDUFA inside the horizon: p*up - (1-p)*down, break-even 0.87
* ``source_reliability``  IBES broker hit-rate as a multiplier on revision_flow, as its own
                          linear term x = x_revision * (m - 1) so Shapley stays exact

`investigator_mag` (``abs_move_exceeds``) is SIZING ONLY: it scales a position,
it never enters E[r]. That is adjudication row 2, enforced by structure (it is
not in `COMPONENTS`) and by test. The regime (`market_sensor`) is a scalar on
every weight, not a name-level term.

WEIGHTS COME FROM FORWARD GRADES, NEVER BY HAND
===============================================
Each component's skill is its held-out (later half by date) information
coefficient against the realised relative return, over ITS OWN graded rows:
decision-ledger SCORED rows that carried its x, and for the two forecast arms
their own ``beats_benchmark`` rows in `predictions.jsonl`. `forecast_reputation`'s
recipe does the rest (``n/(n+k) * skill``, floor 0, gamma, normalised). A
component with fewer than `ER_MIN_GRADED` graded DATE blocks is shrunk to the
prior -- half an equal share -- not zeroed and not trusted.

The equal-weight blend is computed and printed beside the reputation blend on
every row (the forecast-combination puzzle: estimated weights beat equal weights
by little and lose when n is small). `u_plan` uses the reputation blend only when
`oos_advantage_reputation_vs_equal` -- rolling, held out by date -- is positive
over at least `ER_OOS_MIN_DATES` dates and survives dropping any one year.

No LLM, no network except the regime's VIX (FRED, through `market_sensor`, in
production only), no new collector, no change to `xs_ranker.FEATURES`.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from backend import config
from backend.services import forecast_reputation as fr

logger = logging.getLogger(__name__)

COMPONENTS: tuple[str, ...] = ("ranker", "revision_flow", "investigator_dir",
                               "thesis_card", "catalyst", "source_reliability")
SIZING_ONLY: tuple[str, ...] = ("investigator_mag",)
#: Components whose skill is graded from `predictions.jsonl` (their own
#: forecast rows), not from decision-ledger rows -- counting both would grade
#: one forecast twice.
FORECAST_GRADED: dict[str, str] = {"investigator_dir": "investigator:",
                                   "thesis_card": "thesis_card:"}
RECEIPT_SUBDIR = "expected_return"

#: yfinance firm name -> IBES `estimid`. Only mappings that are unambiguous;
#: an unmapped firm is neutral (multiplier 1), never guessed.
FIRM_TO_ESTIMID: dict[str, str] = {
    "Goldman Sachs": "GOLDMAN", "JP Morgan": "JPMORGAN", "B of A Securities": "MERRILL",
    "Raymond James": "RAYMOND", "Piper Sandler": "PIPER", "RBC Capital": "RBCDOMIN",
    "Evercore ISI Group": "EVERCO", "Stifel": "STIFEL", "Needham": "NEEDHAM",
    "Mizuho": "MIZUSEC", "HC Wainwright & Co.": "HCWAIN", "DA Davidson": "DAVIDSON",
    "Canaccord Genuity": "CANACCOR", "Credit Suisse": "FBOSTON", "Morgan Stanley": "MORGAN",
}


# ═══════════════════════════════ sources ════════════════════════════════════

@dataclass
class Sources:
    """Everything the layer reads, loaded once. A field left None is a source
    that was NOT read; `unavailable` says why, by name, so an asleep component
    is never mistaken for a component with nothing to say."""
    label: str = "custom"
    ranking: dict | None = None
    predictions: list[dict] | None = None
    decision_rows: list[dict] | None = None
    revisions: pd.DataFrame | None = None
    sweep: dict | None = None
    cards: list[dict] | None = None
    catalysts: list[dict] | None = None
    regime: dict | None = None
    ibes: pd.DataFrame | None = None
    unavailable: dict[str, str] = field(default_factory=dict)
    vintage: dict[str, str] = field(default_factory=dict)

    @classmethod
    def sandbox(cls, *, out: Path, decision_ledger: Path | None) -> "Sources":
        """Only what lives beside an injected ledger: `out/ranking.json` and
        that ledger. A caller that injects its own decision ledger is running a
        sandbox; mixing it with the production forecast ledger would grade a
        test's decisions against real forecasts."""
        from backend.services import decision_ledger as DL
        s = cls(label="sandbox")
        s.ranking = _read_json(Path(out) / "ranking.json")
        if s.ranking is None:
            s.unavailable["ranking"] = f"no ranking.json in {out}"
        s.decision_rows = DL.read(decision_ledger)
        for k in ("predictions", "revisions", "sweep", "cards", "catalysts",
                  "regime", "ibes"):
            s.unavailable[k] = "sandbox: the production store is not read"
        return s

    @classmethod
    def production(cls, *, asof: str, out: Path | None,
                   decision_ledger: Path | None = None,
                   with_regime: bool = True) -> "Sources":
        """Read-only loads of the real stores. Each failure is named."""
        from backend.services import decision_ledger as DL
        root = Path(config.OPTIMUS_LEDGER_DIR)
        s = cls(label="production")

        def _try(name: str, fn):
            try:
                return fn()
            except Exception as exc:                               # noqa: BLE001
                s.unavailable[name] = f"{type(exc).__name__}: {str(exc)[:160]}"
                return None

        if out is not None:
            s.ranking = _read_json(Path(out) / "ranking.json")
            if s.ranking is None:
                s.unavailable["ranking"] = f"no ranking.json in {out}"
        s.predictions = _try("predictions", lambda: fr.load_ledger(root / "predictions.jsonl"))
        s.decision_rows = _try("decision_rows", lambda: DL.read(decision_ledger))
        s.revisions = _try("revisions", lambda: pd.read_parquet(
            root / "analyst" / "target_revisions.parquet",
            columns=["ticker", "event_date", "firm", "target_action", "prior_target",
                     "current_target", "pit_safe"]))
        sw = _latest_dated(root / "analyst", "revision_flow_sweep_", asof)
        if sw is None:
            s.unavailable["sweep"] = f"no revision_flow_sweep_<date>.json on or before {asof}"
        else:
            s.sweep = _read_json(sw)
            s.vintage["sweep"] = sw.name
        s.cards = _try("cards", lambda: _load_cards(asof, s.vintage))
        s.catalysts = _try("catalysts", lambda: _load_catalysts(root / "pm_catalysts", asof))
        s.ibes = _try("ibes", lambda: pd.read_parquet(
            root / "actor_corpus" / "ibes_graded.parquet", columns=["estimid", "outcome"]))
        if with_regime:
            s.regime = _try("regime", lambda: _regime(asof))
        else:
            s.unavailable["regime"] = "not requested"
        return s


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _latest_dated(folder: Path, prefix: str, asof: str, suffix: str = ".json") -> Path | None:
    if not folder.is_dir():
        return None
    best = None
    for p in folder.glob(f"{prefix}*{suffix}"):
        stamp = p.name[len(prefix):len(p.name) - len(suffix)][:10]
        if len(stamp) == 10 and stamp <= asof and (best is None or stamp > best[0]):
            best = (stamp, p)
    return best[1] if best else None


def _load_cards(asof: str, vintage: dict) -> list[dict]:
    from backend.services import thesis_card as TC
    root = TC.cards_root()
    days = sorted(p.name for p in root.iterdir()
                  if p.is_dir() and len(p.name) == 10 and p.name <= asof) if root.is_dir() else []
    if not days:
        return []
    vintage["cards"] = days[-1]
    return [c for c in TC.read_cards(days[-1], root=root) if not c.get("_unreadable")]


def _load_catalysts(folder: Path, asof: str) -> list[dict]:
    import yaml
    out: list[dict] = []
    for p in sorted(folder.glob("*.yaml")):
        blob = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if str(blob.get("built", "")) > asof:      # a calendar written after asof
            continue
        for r in blob.get("catalysts") or []:
            if isinstance(r, dict) and r.get("ticker") and r.get("date"):
                out.append({**r, "date": str(r["date"])[:10], "source": p.name})
    return out


def _regime(asof: str) -> dict:
    from backend.services import market_sensor as MS
    r = MS.regime(asof)
    return {k: r.get(k) for k in ("regime", "cell", "trend", "vix", "trend_return",
                                  "trend_observed_at", "reason", "vix_refusal")}


# ═══════════════════════════════ small math ═════════════════════════════════

def _alias(h: Any) -> int | None:
    try:
        return config.ER_HORIZON_ALIASES.get(int(h))
    except (TypeError, ValueError):
        return None


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def pdufa_term(p_approval: float) -> float:
    """Expected 5-day return of holding into a PDUFA at `p_approval`.

    ``p*up - (1-p)*down`` with ``down = up * p* / (1 - p*)``, so the term is
    exactly zero at the break-even `ER_PDUFA_BREAKEVEN_P` (0.87) and negative
    below it -- the CRL tail the 2026-09-25 review found no book had priced.
    """
    be = float(config.ER_PDUFA_BREAKEVEN_P)
    up = float(config.ER_PDUFA_UP_RETURN)
    down = up * be / (1.0 - be)
    p = min(max(float(p_approval), 0.0), 1.0)
    return p * up - (1.0 - p) * down


# ═══════════════════════════════ weights ════════════════════════════════════

def component_weights(graded: pd.DataFrame, *, horizon: int) -> pd.DataFrame:
    """Per component at `horizon`: graded date blocks, held-out IC, reputation weight.

    `graded` is long: component, horizon, date, ticker, x, rel. Skill is the
    Pearson IC of x against the realised relative return on the LATER half of
    the component's dates (forecast_reputation's held-out convention). ``n`` for
    the shrink is the number of graded DATE blocks (CANON §58), not rows.
    `rep_weight` is `forecast_reputation.weights` over the GRADED components
    only; the ungraded sit at the prior inside `blend`.
    """
    recs = {}
    g = graded[pd.to_numeric(graded.get("horizon"), errors="coerce") == horizon] \
        if len(graded) else graded
    for c in COMPONENTS:
        sub = g[g["component"] == c] if len(g) else g
        sub = sub[np.isfinite(sub["x"].astype(float)) & np.isfinite(sub["rel"].astype(float))] \
            if len(sub) else sub
        dates = sorted(sub["date"].astype(str).unique()) if len(sub) else []
        n = len(dates)
        test = sub[sub["date"].astype(str).isin(dates[n // 2:])] if n else sub
        ic = _corr(test["x"].to_numpy(float), test["rel"].to_numpy(float)) if n else float("nan")
        recs[c] = {"n_dates": n, "n_rows": int(len(sub)), "n": float(n),
                   "skill": ic, "graded": n >= int(config.ER_MIN_GRADED)}
    t = pd.DataFrame.from_dict(recs, orient="index")
    t["rep_weight"] = 0.0
    gr = t[t["graded"]]
    if len(gr):
        w = fr.weights(gr, k_prior=float(config.ER_K_PRIOR), gamma=float(config.ER_GAMMA),
                       floor=float(config.ER_FLOOR))
        t.loc[w.index, "rep_weight"] = w.values
    return t


def blend(x: dict[str, float | None], table: pd.DataFrame, *, regime_scale: float = 1.0,
          baseline: dict[str, float] | None = None,
          asleep_reasons: dict[str, str] | None = None) -> dict:
    """Both blends for one name, with the exact Shapley vector of each.

    A component whose x is None is ASLEEP: excluded, named, and the awake
    weights renormalise to 1 (sleeping experts). Ungraded awake components get
    `ER_PRIOR_SHARE` of an equal share; graded ones split the rest by
    reputation. If every graded awake component has zero reputation and none is
    ungraded, the reputation blend is UNDEFINED (not an average of anti-signal)
    and the row says so.
    """
    asleep_reasons = asleep_reasons or {}
    baseline = baseline or {}
    awake = [c for c in COMPONENTS if x.get(c) is not None and math.isfinite(float(x[c]))]
    asleep = {c: asleep_reasons.get(c, "no input for this name on this date")
              for c in COMPONENTS if c not in awake}
    n = len(awake)
    w_eq = {c: 1.0 / n for c in awake} if n else {}
    graded = [c for c in awake if bool(table.loc[c, "graded"])] if n else []
    ungraded = [c for c in awake if c not in graded]
    rep_defined = True
    if not graded:
        w_rep = dict(w_eq)
    else:
        prior = float(config.ER_PRIOR_SHARE) / n
        raw = {c: prior for c in ungraded}
        gw = {c: float(table.loc[c, "rep_weight"]) for c in graded}
        tot = sum(gw.values())
        mass = 1.0 - prior * len(ungraded)
        for c in graded:
            raw[c] = mass * gw[c] / tot if tot > 0 else 0.0
        s = sum(raw.values())
        if s > 0:
            w_rep = {c: raw[c] / s for c in awake}
        else:
            w_rep, rep_defined = {c: 0.0 for c in awake}, False

    def _one(w: dict) -> tuple[float | None, dict, float]:
        if not awake or (w is w_rep and not rep_defined):
            return None, {c: 0.0 for c in awake}, 0.0
        er = regime_scale * sum(w[c] * float(x[c]) for c in awake)
        phi = {c: regime_scale * w[c] * (float(x[c]) - float(baseline.get(c, 0.0)))
               for c in awake}
        bl = regime_scale * sum(w[c] * float(baseline.get(c, 0.0)) for c in awake)
        return er, phi, bl

    er_r, phi_r, bl_r = _one(w_rep)
    er_e, phi_e, bl_e = _one(w_eq)
    return {"awake": awake, "asleep": asleep, "graded": graded,
            "weights_reputation": w_rep, "weights_equal": w_eq,
            "reputation_defined": rep_defined, "regime_scale": regime_scale,
            "er_reputation": er_r, "phi_reputation": phi_r, "baseline_reputation": bl_r,
            "er_equal": er_e, "phi_equal": phi_e, "baseline_equal": bl_e}


def oos_advantage(wide: pd.DataFrame, *, horizon: int) -> dict:
    """Rolling, held out by date: IC of the reputation blend minus IC of the
    equal blend, each date scored with weights fit ONLY on earlier dates.

    `wide` rows: date, ticker, rel, and one column per component (NaN = asleep).
    `licensed` needs >= `ER_OOS_MIN_DATES` evaluable dates, a positive mean, and
    a positive mean after dropping any single year.
    """
    base = {"horizon": horizon, "n_dates": 0, "oos_advantage_reputation_vs_equal": None,
            "by_year": {}, "loo_worst": None, "licensed": False}
    if wide is None or wide.empty:
        return {**base, "why": "no graded decision rows carry an E[r] decomposition yet"}
    wide = wide.copy()
    wide["date"] = wide["date"].astype(str)
    dates = sorted(wide["date"].unique())
    diffs = []
    for i, d in enumerate(dates[1:], start=1):
        train = wide[wide["date"] < d]
        long = train.melt(id_vars=["date", "ticker", "rel"], value_vars=list(COMPONENTS),
                          var_name="component", value_name="x").dropna(subset=["x"])
        long["horizon"] = horizon
        t = component_weights(long, horizon=horizon)
        test = wide[wide["date"] == d]
        if len(test) < 3:
            continue
        er_r, er_e = [], []
        for _, r in test.iterrows():
            b = blend({c: (None if pd.isna(r.get(c)) else float(r[c])) for c in COMPONENTS}, t)
            er_r.append(b["er_reputation"] if b["er_reputation"] is not None else np.nan)
            er_e.append(b["er_equal"] if b["er_equal"] is not None else np.nan)
        rel = test["rel"].to_numpy(float)
        a, e = np.array(er_r, float), np.array(er_e, float)
        ok = np.isfinite(a) & np.isfinite(e) & np.isfinite(rel)
        ic_r, ic_e = _corr(a[ok], rel[ok]), _corr(e[ok], rel[ok])
        if math.isfinite(ic_r) and math.isfinite(ic_e):
            diffs.append((d, ic_r - ic_e))
    if not diffs:
        return {**base, "why": "no date with >= 3 graded names and both blends defined"}
    df = pd.DataFrame(diffs, columns=["date", "diff"])
    df["year"] = df["date"].str[:4]
    by_year = df.groupby("year")["diff"].mean().to_dict()
    loo = ({y: float(df[df["year"] != y]["diff"].mean()) for y in by_year}
           if len(by_year) > 1 else {})
    adv = float(df["diff"].mean())
    loo_worst = min(loo.values()) if loo else adv
    lic = (len(df) >= int(config.ER_OOS_MIN_DATES) and adv > 0 and loo_worst > 0)
    return {**base, "n_dates": int(len(df)), "oos_advantage_reputation_vs_equal": adv,
            "by_year": {k: float(v) for k, v in by_year.items()}, "loo_worst": loo_worst,
            "licensed": bool(lic),
            "why": (f"{len(df)} evaluable dates (need {config.ER_OOS_MIN_DATES}); "
                    f"advantage {adv:+.4f}, LOO-worst {loo_worst:+.4f}")}


# ═══════════════════════════════ fit / refit ════════════════════════════════

def _graded_forecasts(preds: list[dict] | None, asof: str) -> pd.DataFrame:
    if not preds:
        return fr.graded_frame_from_rows([])
    g = fr.graded_frame_from_rows(preds)
    return g[g["made_day"].astype(str) <= asof]


def _decision_frames(rows: list[dict] | None, asof: str) -> tuple[pd.DataFrame, dict]:
    """SCORED decision rows that carried a decomposition -> (long, wide per h)."""
    long_rows, wide_rows = [], {h: [] for h in config.ER_HORIZONS}
    for r in rows or []:
        d = r.get("detail") or {}
        if str(r.get("state")) != "SCORED" or not isinstance(d, dict):
            continue
        comp = d.get("er_by_component")
        rel = _f(d.get("excess_return"))
        h = _alias(d.get("er_horizon") or d.get("horizon_sessions"))
        day = str(r.get("asof") or "")[:10]
        if not isinstance(comp, dict) or rel is None or h is None or not day or day > asof:
            continue
        wr = {"date": day, "ticker": d.get("ticker"), "rel": rel}
        for c in COMPONENTS:
            xv = _f((comp.get(c) or {}).get("x")) if isinstance(comp.get(c), dict) else None
            wr[c] = np.nan if xv is None else xv
            if xv is not None and c not in FORECAST_GRADED:
                long_rows.append({"component": c, "horizon": h, "date": day,
                                  "ticker": d.get("ticker"), "x": xv, "rel": rel})
        wide_rows[h].append(wr)
    long = pd.DataFrame(long_rows, columns=["component", "horizon", "date", "ticker", "x", "rel"])
    wide = {h: pd.DataFrame(v, columns=["date", "ticker", "rel", *COMPONENTS])
            for h, v in wide_rows.items()}
    return long, wide


def _forecast_long(g: pd.DataFrame) -> pd.DataFrame:
    """Direction rows ONLY (`beats_benchmark`) for the two forecast components."""
    out = []
    if g.empty:
        return pd.DataFrame(columns=["component", "horizon", "date", "ticker", "x", "rel"])
    d = g[g["observable"].astype(str) == fr.DIRECTION_OBSERVABLE]
    for comp, prefix in FORECAST_GRADED.items():
        sub = d[d["arm"].astype(str).str.startswith(prefix)]
        for _, r in sub.iterrows():
            h = _alias(r["horizon_days"])
            if h is None or not np.isfinite(r["rel_ret"]):
                continue
            out.append({"component": comp, "horizon": h, "date": r["made_day"],
                        "ticker": r["ticker"], "x": float(r["p"]), "rel": float(r["rel_ret"])})
    return pd.DataFrame(out, columns=["component", "horizon", "date", "ticker", "x", "rel"])


def _calibration(g: pd.DataFrame) -> dict:
    """p-bin -> realised relative return, per forecast component and horizon."""
    out: dict = {}
    if g.empty:
        return out
    d = g[(g["observable"].astype(str) == fr.DIRECTION_OBSERVABLE) & np.isfinite(g["rel_ret"])]
    for comp, prefix in FORECAST_GRADED.items():
        sub = d[d["arm"].astype(str).str.startswith(prefix)].copy()
        sub["h"] = sub["horizon_days"].map(_alias)
        for h, s in sub.groupby("h"):
            k = min(10, len(s))
            if k < 2:
                continue
            bins = pd.qcut(s["p"], k, labels=False, duplicates="drop")
            rows = [{"p_lo": float(b["p"].min()), "p_hi": float(b["p"].max()),
                     "p_mean": float(b["p"].mean()), "n": int(len(b)),
                     "rel_mean": float(b["rel_ret"].mean())}
                    for _, b in s.groupby(bins, sort=True)]
            out.setdefault(comp, {})[int(h)] = {
                "n_total": int(len(s)), "n_dates": int(s["made_day"].nunique()), "bins": rows}
    return out


def _calib_lookup(cal: dict, p: float) -> tuple[float, int]:
    bins = cal["bins"]
    hit = [b for b in bins if b["p_lo"] <= p <= b["p_hi"]]
    b = hit[0] if hit else min(bins, key=lambda b: abs(b["p_mean"] - p))
    k = float(config.ER_CALIB_K)
    return b["n"] / (b["n"] + k) * b["rel_mean"], int(b["n"])


def _magnitude(g: pd.DataFrame) -> dict:
    """The investigator family's MAGNITUDE skill and p -> |move| table (sizing only)."""
    base = {"lambda": 0.0, "skill": None, "n": 0, "bins": [], "ref_abs_move": None,
            "horizon": 5}
    if g.empty:
        return {**base, "why": "no graded forecasts"}
    m = g[(g["observable"].astype(str) == fr.MAGNITUDE_OBSERVABLE)
          & g["arm"].astype(str).str.startswith("investigator:")
          & (pd.to_numeric(g["horizon_days"], errors="coerce") == 5)
          & np.isfinite(g["ret"])].copy()
    if len(m) < 2:
        return {**base, "why": "fewer than two graded abs_move_exceeds rows at h=5"}
    m["arm"] = "investigator"
    sk = fr.magnitude_skill(m)
    skill = float(sk["skill"].iloc[0]) if len(sk) else float("nan")
    n = int(m["made_day"].nunique())
    lam = 0.0
    if math.isfinite(skill):
        lam = min(max(n / (n + float(config.ER_K_PRIOR)) * skill, 0.0), 1.0)
    m["absret"] = m["ret"].abs()
    k = min(10, len(m))
    bins = pd.qcut(m["p"], k, labels=False, duplicates="drop")
    rows = [{"p_lo": float(b["p"].min()), "p_hi": float(b["p"].max()),
             "p_mean": float(b["p"].mean()), "n": int(len(b)),
             "abs_move": float(b["absret"].mean())} for _, b in m.groupby(bins, sort=True)]
    return {**base, "lambda": lam, "skill": skill, "n": n, "bins": rows,
            "ref_abs_move": float(m["absret"].mean()),
            "why": "lambda = clip(n/(n+k) * held-out Brier skill on abs_move_exceeds, 0, 1)"}


def fit(sources: Sources, *, asof: str) -> dict:
    """Skill tables, calibration, OOS gate and magnitude, from graded rows only."""
    g = _graded_forecasts(sources.predictions, asof)
    dl_long, wide = _decision_frames(sources.decision_rows, asof)
    parts = [f for f in (dl_long, _forecast_long(g)) if len(f)]
    long = (pd.concat(parts, ignore_index=True) if parts else dl_long)
    tables = {h: component_weights(long, horizon=h) for h in config.ER_HORIZONS}
    oos = {h: oos_advantage(wide[h], horizon=h) for h in config.ER_HORIZONS}
    return {"asof": asof, "tables": tables, "oos": oos, "calibration": _calibration(g),
            "magnitude": _magnitude(g), "n_graded_forecasts": int(len(g)),
            "n_graded_decisions": int(sum(len(w) for w in wide.values()))}


def _fit_summary(f: dict) -> dict:
    return {
        "tables": {f"h{h}": {c: {k: (_f(v) if isinstance(v, (float, np.floating)) else
                                     bool(v) if isinstance(v, (bool, np.bool_)) else int(v))
                                 for k, v in row.items()}
                             for c, row in t.to_dict(orient="index").items()}
                   for h, t in f["tables"].items()},
        "oos": {f"h{h}": v for h, v in f["oos"].items()},
        "calibration": {c: {f"h{h}": v for h, v in d.items()}
                        for c, d in f["calibration"].items()},
        "magnitude": f["magnitude"],
        "n_graded_forecasts": f["n_graded_forecasts"],
        "n_graded_decisions": f["n_graded_decisions"],
    }


def receipt_dir(out_dir: Path | str | None = None) -> Path:
    return Path(out_dir) if out_dir is not None else \
        Path(config.OPTIMUS_LEDGER_DIR) / RECEIPT_SUBDIR


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def refit(today: str | None = None, *, sources: Sources | None = None,
          out_dir: Path | str | None = None) -> dict:
    """`u_grade`'s call: re-grade every component and write `refit_<today>.json`.

    Written whether or not anything is graded yet -- a missing receipt is
    indistinguishable from a step that never ran.
    """
    today = today or date.today().isoformat()
    src = sources or Sources.production(asof=today, out=None, with_regime=False)
    f = fit(src, asof=today)
    rec = {"receipt": "expected_return_refit", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0, "date": today,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "sources": src.label, "unavailable": src.unavailable,
           "constants": _constants(), **_fit_summary(f)}
    _write(receipt_dir(out_dir) / f"refit_{today}.json", rec)
    return rec


def _constants() -> dict:
    return {k: getattr(config, k) for k in dir(config) if k.startswith("ER_")}


# ═══════════════════════════════ x per component ════════════════════════════

def _cal_days(h: int) -> int:
    return int(math.ceil(h * 7 / 5))


def catalyst_x(ticker: str, asof: str, horizon: int, events: Iterable[dict], *,
               p_approval: float | None = None) -> tuple[float | None, dict]:
    """The catalyst term: a dated PDUFA strictly after `asof` and inside the
    horizon (in calendar days, h*7/5). Other kinds are recorded, unsigned."""
    t = str(ticker).upper()
    lo = date.fromisoformat(asof)
    hi = lo + timedelta(days=_cal_days(horizon))
    inside = [e for e in events if str(e.get("ticker", "")).upper() == t
              and lo < date.fromisoformat(str(e["date"])[:10]) <= hi]
    signed = [e for e in inside if str(e.get("kind", "")).lower() == "pdufa"]
    unsigned = [f"{e['date']} {e.get('kind')}" for e in inside if e not in signed]
    if not signed:
        return None, {"asleep_reason": f"no dated PDUFA inside {horizon} sessions",
                      "unsigned_events": unsigned}
    src = "card" if p_approval is not None else "prior"
    p = float(p_approval) if p_approval is not None else float(config.ER_PDUFA_PRIOR_P_APPROVAL)
    x = sum(pdufa_term(p) for _ in signed)
    return x, {"events": [f"{e['date']} pdufa {str(e.get('what', ''))[:60]}" for e in signed],
               "p_approval": p, "p_approval_source": src,
               "breakeven_p": float(config.ER_PDUFA_BREAKEVEN_P), "unsigned_events": unsigned}


def _card_events(cards: list[dict] | None) -> tuple[list[dict], dict[str, float]]:
    ev, p_appr = [], {}
    for c in cards or []:
        t = str(c.get("ticker") or "").upper()
        if not t:
            continue
        pa = _f(c.get("p_approval"))
        if pa is not None:
            p_appr[t] = pa
        for s in c.get("upcoming_dates") or []:
            parts = [x.strip() for x in str(s).split("|")]
            if len(parts) >= 2 and len(parts[0]) >= 10:
                try:
                    date.fromisoformat(parts[0][:10])
                except ValueError:
                    continue
                ev.append({"date": parts[0][:10], "ticker": t, "kind": parts[1].lower(),
                           "what": parts[2] if len(parts) > 2 else "", "source": "card"})
    return ev, p_appr


def _latest_p(g: pd.DataFrame, prefix: str, observable: str, asof: str) -> dict:
    """ticker -> {h: mean p on its latest made day <= asof} (ungraded rows too)."""
    if g is None or g.empty:
        return {}
    s = g[g["arm"].astype(str).str.startswith(prefix)
          & (g["observable"].astype(str) == observable)
          & (g["made_day"].astype(str) <= asof)].copy()
    out: dict = {}
    if s.empty:
        return out
    s["h"] = s["horizon_days"].map(_alias) if observable == fr.DIRECTION_OBSERVABLE \
        else pd.to_numeric(s["horizon_days"], errors="coerce")
    for (t, h), sub in s.dropna(subset=["h"]).groupby(["ticker", "h"]):
        last = sub["made_day"].max()
        out.setdefault(str(t).upper(), {})[int(h)] = float(sub[sub["made_day"] == last]["p"].mean())
    return out


def _all_forecasts(preds: list[dict] | None) -> pd.DataFrame:
    """Every forecast row with a probability (graded or not), for today's p."""
    rows = []
    for r in preds or []:
        p = _f(r.get("probability"))
        if p is None:
            continue
        rows.append({"arm": str(r.get("specialist")), "p": p,
                     "observable": r.get("observable"), "horizon_days": r.get("horizon_days"),
                     "ticker": str(r.get("ticker") or "").upper(),
                     "made_day": str(r.get("made_at") or "")[:10]})
    return pd.DataFrame(rows, columns=["arm", "p", "observable", "horizon_days",
                                       "ticker", "made_day"])


def _revision_state(src: Sources, asof: str) -> dict:
    """Flow for every covered ticker at asof, the rule rank, and acting firms."""
    from backend.services import revision_flow as RF
    if src.revisions is None:
        return {"why": src.unavailable.get("revisions", "revisions not read")}
    prep = RF.prepare(src.revisions)
    a = pd.Timestamp(asof)
    lo = a - pd.Timedelta(days=RF.WINDOW_DAYS)
    win = prep[(prep["t"] >= lo) & (prep["t"] < a)]
    flow = RF._stats(win, a)
    rule = RF.rule_score(flow, min_firms=int(config.ER_REVISION_MIN_FIRMS)).sort_values(
        ascending=False)
    rank = {t: i + 1 for i, t in enumerate(rule.index)}
    firms = win.groupby("ticker")["firm"].apply(lambda s: sorted(set(s))).to_dict()
    return {"flow": flow, "rank": rank, "firms": firms, "n_ranked": len(rank)}


def _revision_table(sweep: dict | None, h: int) -> dict[int, float] | None:
    if not sweep:
        return None
    rb = sweep.get("rule_backtest") or {}
    out = {}
    for k in (20, 50):
        cell = rb.get(f"H{h}_k{k}")
        if isinstance(cell, dict) and _f(cell.get("mean_vs_covered_ew_per_hold")) is not None:
            out[k] = float(cell["mean_vs_covered_ew_per_hold"])
    return out or None


def _ibes_reliability(ibes: pd.DataFrame | None) -> tuple[dict[str, float], float] | None:
    if ibes is None or ibes.empty:
        return None
    base = float(ibes["outcome"].mean())
    k = float(config.ER_K_PRIOR)
    g = ibes.groupby("estimid")["outcome"].agg(["mean", "size"])
    rel = ((g["size"] * g["mean"] + k * base) / (g["size"] + k)).to_dict()
    return {str(e): float(v) for e, v in rel.items()}, base


# ═══════════════════════════════ build ══════════════════════════════════════

def build(asof: str, tickers: Iterable[str], sources: Sources, *,
          fitted: dict | None = None, out_dir: Path | str | None = None,
          write: bool = True) -> dict:
    """E[r] at every horizon for every ticker, both blends, phi, sizing scale.

    Writes `er_<asof>.json` (per name: E[r] by h, phi vector, awake set,
    weights, source) unless `write=False`.
    """
    tickers = list(dict.fromkeys(str(t).upper() for t in tickers if t))
    fitted = fitted or fit(sources, asof=asof)
    reg = dict(sources.regime or {"regime": "unknown",
                                  "reason": sources.unavailable.get("regime", "not read")})
    reg_label = str(reg.get("regime") or "unknown")
    scale = float(config.ER_REGIME_SCALE.get(reg_label, 1.0))
    reg["scale"] = scale

    allf = _all_forecasts(sources.predictions)
    inv_p = _latest_p(allf, "investigator:", fr.DIRECTION_OBSERVABLE, asof)
    card_p = _latest_p(allf, "thesis_card:", fr.DIRECTION_OBSERVABLE, asof)
    mag_p = _latest_p(allf, "investigator:", fr.MAGNITUDE_OBSERVABLE, asof)
    rank_top = {str(r.get("symbol")).upper(): r for r in (sources.ranking or {}).get("top") or []}
    try:
        rev = _revision_state(sources, asof)
    except Exception as exc:                                       # noqa: BLE001
        rev = {"why": f"revision_flow refused: {type(exc).__name__}: {str(exc)[:160]}"}
    rel_tab = _ibes_reliability(sources.ibes)
    card_ev, card_pa = _card_events(sources.cards)
    events = list(sources.catalysts or []) + card_ev

    names: dict[str, dict] = {t: {} for t in tickers}
    per_h_x: dict[int, dict[str, dict]] = {}
    for h in config.ER_HORIZONS:
        xs: dict[str, dict] = {}
        for t in tickers:
            x: dict[str, float | None] = {c: None for c in COMPONENTS}
            why: dict[str, str] = {}
            det: dict[str, Any] = {}
            # ranker
            r = rank_top.get(t)
            if h != 21:
                why["ranker"] = "the ranker is calibrated at 21 sessions only"
            elif r is None:
                why["ranker"] = ("not in ranking.json's top list" if sources.ranking
                                 else sources.unavailable.get("ranking", "no ranking"))
            elif not r.get("calibration_measured", True):
                why["ranker"] = "decile not calibrated"
            else:
                x["ranker"] = _f(r.get("expected_relative_return_21d_net"))
                det["ranker"] = {"decile": r.get("decile"), "rank": r.get("rank")}
            # revision_flow (+ source_reliability as its own linear term)
            table = _revision_table(sources.sweep, h)
            if "flow" not in rev:
                why["revision_flow"] = rev.get("why", "revisions unavailable")
            elif table is None:
                why["revision_flow"] = f"no measured rule table at h={h}"
            elif t not in rev["flow"].index:
                why["revision_flow"] = "no revision event in the 90-day window"
            elif t not in rev["rank"]:
                why["revision_flow"] = f"fewer than {config.ER_REVISION_MIN_FIRMS} firms acted"
            else:
                rk = rev["rank"][t]
                x["revision_flow"] = (table.get(20) if rk <= 20 and 20 in table else
                                      table.get(50) if rk <= 50 and 50 in table else 0.0)
                fl = rev["flow"].loc[t]
                det["revision_flow"] = {"rule_rank": rk, "of": rev["n_ranked"],
                                        "net_raises": _f(fl["net_raises"]),
                                        "n_firms": _f(fl["n_firms"])}
            if x["revision_flow"] is None:
                why["source_reliability"] = "revision_flow is asleep"
            elif rel_tab is None:
                why["source_reliability"] = sources.unavailable.get("ibes", "IBES not read")
            else:
                rmap, base = rel_tab
                mapped = [rmap[FIRM_TO_ESTIMID[f]] for f in rev["firms"].get(t, [])
                          if f in FIRM_TO_ESTIMID and FIRM_TO_ESTIMID[f] in rmap]
                if not mapped:
                    why["source_reliability"] = "no acting firm maps to an IBES broker"
                else:
                    m = min(max(float(np.mean(mapped)) / base, config.ER_SR_MULT_MIN),
                            config.ER_SR_MULT_MAX)
                    x["source_reliability"] = float(x["revision_flow"]) * (m - 1.0)
                    det["source_reliability"] = {"multiplier": m, "n_mapped_firms": len(mapped)}
            # investigator direction
            p = (inv_p.get(t) or {}).get(h)
            cal = (fitted["calibration"].get("investigator_dir") or {}).get(h)
            if p is None:
                why["investigator_dir"] = f"no investigator beats_benchmark row at h={h}"
            elif cal is None:
                why["investigator_dir"] = f"no graded calibration at h={h} (p={p:.3f} carried)"
                det["investigator_dir"] = {"p": p}
            else:
                x["investigator_dir"], nb = _calib_lookup(cal, p)
                det["investigator_dir"] = {"p": p, "bin_n": nb}
            # thesis card
            p = (card_p.get(t) or {}).get(h)
            cal = (fitted["calibration"].get("thesis_card") or {}).get(h)
            if p is None:
                why["thesis_card"] = f"no thesis_card row at h={h}"
            elif cal is None or cal["n_total"] < int(config.ER_MIN_GRADED):
                n = 0 if cal is None else cal["n_total"]
                why["thesis_card"] = (f"{n} graded of {config.ER_MIN_GRADED}: asleep "
                                      f"(p={p:.3f} carried)")
                det["thesis_card"] = {"p": p}
            else:
                x["thesis_card"], nb = _calib_lookup(cal, p)
                det["thesis_card"] = {"p": p, "bin_n": nb}
            # catalyst
            if sources.catalysts is None and sources.cards is None:
                why["catalyst"] = sources.unavailable.get("catalysts", "no calendar read")
            else:
                cx, cdet = catalyst_x(t, asof, h, events, p_approval=card_pa.get(t))
                x["catalyst"] = cx
                det["catalyst"] = cdet
                if cx is None:
                    why["catalyst"] = cdet["asleep_reason"]
            xs[t] = {"x": x, "why": why, "det": det}
        per_h_x[h] = xs

    # baseline per component = mean x over the names where it is awake (per h)
    source_by_h = {h: ("reputation" if fitted["oos"][h].get("licensed") else "equal")
                   for h in config.ER_HORIZONS}
    for h, xs in per_h_x.items():
        base = {}
        for c in COMPONENTS:
            vals = [v["x"][c] for v in xs.values() if v["x"][c] is not None]
            base[c] = float(np.mean(vals)) if vals else 0.0
        tab = fitted["tables"][h]
        for t, v in xs.items():
            b = blend(v["x"], tab, regime_scale=scale, baseline=base, asleep_reasons=v["why"])
            src = source_by_h[h]
            if src == "reputation" and not b["reputation_defined"]:
                src = "equal"
            kind = "reputation" if src == "reputation" else "equal"
            er = b[f"er_{kind}"]
            if er is not None:
                assert abs(sum(b[f"phi_{kind}"].values()) + b[f"baseline_{kind}"] - er) < 1e-12
            names[t][f"h{h}"] = {
                "er": er, "er_reputation": b["er_reputation"], "er_equal": b["er_equal"],
                "weights_source": src,
                "weights": b[f"weights_{kind}"],
                "weights_reputation": b["weights_reputation"],
                "weights_equal": b["weights_equal"],
                "phi": b[f"phi_{kind}"], "baseline": b[f"baseline_{kind}"],
                "x": {c: v["x"][c] for c in b["awake"]},
                "components_awake": b["awake"], "asleep": b["asleep"],
                "detail": v["det"]}

    mag = fitted["magnitude"]
    for t in tickers:
        p = (mag_p.get(t) or {}).get(5)
        if p is None or not mag["bins"] or not mag["ref_abs_move"] or mag["lambda"] <= 0:
            names[t]["size_scale_mag"] = 1.0
            names[t]["size_scale_mag_why"] = ("no abs_move_exceeds forecast for this name"
                                              if p is None else
                                              f"magnitude skill not positive: {mag.get('why')}")
            continue
        bins = mag["bins"]
        hit = [b for b in bins if b["p_lo"] <= p <= b["p_hi"]]
        b = hit[0] if hit else min(bins, key=lambda b: abs(b["p_mean"] - p))
        raw = min(max(mag["ref_abs_move"] / max(b["abs_move"], 1e-9),
                      float(config.ER_SIZE_SCALE_MIN)), 1.0)
        names[t]["size_scale_mag"] = 1.0 - mag["lambda"] * (1.0 - raw)
        names[t]["size_scale_mag_why"] = (f"p(|move|>thr)={p:.2f} -> predicted |move| "
                                          f"{b['abs_move']:.3f} vs ref {mag['ref_abs_move']:.3f}, "
                                          f"lambda {mag['lambda']:.2f}")
    for t in tickers:
        names[t]["size_scale"] = min(1.0, names[t]["size_scale_mag"] * min(scale, 1.0))

    view = {"receipt": "expected_return", "licence": "PRODUCT_EXPERIMENT",
            "llm_spend_usd": 0.0, "asof": asof,
            "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": sources.label, "unavailable": sources.unavailable,
            "calibration_vintage": {**sources.vintage, "fit_asof": fitted["asof"]},
            "regime": reg, "weights_source": {f"h{h}": s for h, s in source_by_h.items()},
            "formula": ("E[r_h] = regime_scale * sum_c w_c x_c over awake c; "
                        "phi_c = regime_scale * w_c (x_c - mean_c); sum phi + baseline = E[r]"),
            "components": list(COMPONENTS), "sizing_only": list(SIZING_ONLY),
            "n_names": len(tickers), "fit": _fit_summary(fitted), "names": names}
    if write:
        p = receipt_dir(out_dir) / f"er_{asof}.json"
        _write(p, view)
        view["path"] = str(p)
    return view


def row_fields(view: dict | None, ticker: str, horizon: int) -> dict:
    """The decision-ledger fields for one (ticker, horizon). Present even when
    the layer had nothing -- an absent key and an asleep layer must not look alike."""
    h = _alias(horizon) if int(horizon) not in config.ER_HORIZONS else int(horizon)
    base = {"er_total": None, "er_equal": None, "er_by_component": {}, "weights": {},
            "weights_source": None, "components_awake": [], "regime": None,
            "er_horizon": h}
    if not view:
        return {**base, "er_absent": "the expected-return layer did not run"}
    cell = ((view.get("names") or {}).get(str(ticker).upper()) or {}).get(f"h{h}") if h else None
    base["regime"] = (view.get("regime") or {}).get("regime")
    if not cell:
        return {**base, "er_absent": f"no E[r] at h={horizon} (E[r] horizons "
                                      f"{list(config.ER_HORIZONS)})"}
    return {"er_total": cell["er"], "er_equal": cell["er_equal"],
            "er_by_component": {c: {"x": cell["x"].get(c), "weight": cell["weights"].get(c),
                                    "phi": cell["phi"].get(c)} for c in cell["components_awake"]},
            "weights": cell["weights"], "weights_source": cell["weights_source"],
            "components_awake": cell["components_awake"], "regime": base["regime"],
            "er_horizon": h, "calibration_vintage": view.get("calibration_vintage")}


def format_top(view: dict, *, n: int = 10, horizon: int = 21) -> str:
    """The plan receipt's print: top-n E[r] with the phi decomposition."""
    k = f"h{horizon}"
    rows = [(t, v[k]) for t, v in (view.get("names") or {}).items()
            if v.get(k) and v[k]["er"] is not None]
    rows.sort(key=lambda r: -r[1]["er"])
    abbrev = {"ranker": "rk", "revision_flow": "rev", "investigator_dir": "inv",
              "thesis_card": "card", "catalyst": "cat", "source_reliability": "src"}
    ws = (view.get("weights_source") or {}).get(k)
    lines = [f"E[r_{horizon}] top {min(n, len(rows))} of {len(rows)} priced "
             f"(weights {ws}, regime {(view.get('regime') or {}).get('regime')} "
             f"x{(view.get('regime') or {}).get('scale')}):"]
    for t, c in rows[:n]:
        phi = " ".join(f"{abbrev[k2]}{v*100:+.2f}" for k2, v in c["phi"].items())
        lines.append(f"{t:<10}{c['er']*100:+6.2f}%  eq {c['er_equal']*100:+6.2f}%  "
                     f"base {c['baseline']*100:+.2f}  phi[{phi}]")
    return "\n".join(lines)


__all__ = ["COMPONENTS", "SIZING_ONLY", "Sources", "blend", "build", "catalyst_x",
           "component_weights", "fit", "format_top", "oos_advantage", "pdufa_term",
           "receipt_dir", "refit", "row_fields"]
