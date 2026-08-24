"""REVISION-FORECASTER-1 — is the mediator easier to learn than the outcome?

PRE-REGISTERED: `Aegis module/TRIALS/PREREG_REVISION_FORECASTER_1.md`, corpse-
linted PASS, committed `d81577e` BEFORE this file existed and before the target
column existed anywhere. Read it first; the decision rule lives there and is not
restated here in a form that could drift from it.

Roadmap item C of the 2026-08-24 external review:

    event state  ->  the NEXT analyst consensus revision  ->  the price response

instead of event state -> return, which `EVENT-RESPONSE-1` asked and answered
STOP. The claim under test is NOT that revisions matter. It is that **the
revision is an easier thing to learn than the return**, so a model trained on
the mediator may rank returns better than one trained on the outcome.

THREE IMPLEMENTATION DECISIONS THE PREREG DID NOT PIN
=====================================================
Recorded here, before any number exists, because a choice made after seeing a
result is a different object from one made before it.

1. **SIGN CONVENTION.** The evaluation target is `drift_k = sign(gap) x
   excess return`, so the routed target is `sign(gap) x revision` — "did the
   analysts move in the direction the market gapped". Both then share one
   convention and the comparison is apples-to-apples. Forced by comparability,
   not chosen from results. The RAW-revision variant is computed and reported
   as a secondary so the choice is visible rather than load-bearing.

2. **21-SESSION FORWARD RETURNS are computed here**, because v1's
   `forward_returns` reads its own frozen `SPEC["horizons_sessions"]` = [1,2,5]
   and mutating another trial's frozen declaration — even temporarily — is
   exactly the tampering the registry exists to make visible. The arithmetic is
   transcribed, and `test_revision_forecaster.py` asserts this file's `fwd5`
   reproduces v1's `fwd5` on the cached panel to 1e-12. If that ever fails, the
   transcription drifted and every number here is void.

3. **`t1` MUST CARRY THE SAME `fpedats` AS `t0`.** IBES rolls the FY1 pointer,
   so a naive `meanest_t1 - meanest_t0` compares an FY2013 estimate to an
   FY2014 one across a fiscal roll. That is not a revision; it is the single
   most efficient way to manufacture a target out of nothing, and it would
   correlate with the calendar and therefore with returns.

BARRED, and checked rather than trusted
=======================================
`actual` and `anndats_act` in the IBES consensus rows are the realised EPS and
its announcement date FOR THE FORECAST PERIOD, which is in the future at the
event. Neither may be a feature. Nothing measured at `t1` may be a feature —
it is inside the target. `feature_leakage_guard.assert_no_target_leakage` runs
before a single model is fitted.

USAGE
    python -m scripts.revision_forecaster_v1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
PANEL = REPO / "backend" / "data" / "optimus" / "event_response" / \
    "event_panel_cache.parquet"
OUT = REPO / "backend" / "data" / "optimus" / "revision_forecaster"

TRIAL_ID = "REVISION-FORECASTER-1"
PREREG = "Aegis module/TRIALS/PREREG_REVISION_FORECASTER_1.md @ d81577e"

#: Frozen in the pre-registration. Restated as code so a drift between the two
#: is a test failure rather than a reading error.
FROZEN = {
    "fpi": "1",
    "measure": "EPS",
    "t1_min_days_after_event": 5,
    "t1_max_days_after_event": 45,
    "primary_horizon_sessions": 21,
    "reported_horizon_sessions": 5,
    "first_test_year": 2012,
    "models": ["ridge", "lightgbm"],
    "min_estimates": 3,
    "scaling": "revision / price at the session before the event",
    "fpedats_must_match": True,
    "n_effective": "EVENT MONTHS (date blocks) — CANON §58",
    "declared_effect_size": 0.025,
    "paired_mde80_at_rho_0.8": 0.0158,
    "one_se_screen_bar": True,
}

FEATURES = [
    "numeric_surprise_pct", "surprise_scaled", "expectation_dispersion",
    "n_estimates", "pre_event_price_runup", "overnight_gap", "abs_gap",
    "gap_vs_runup", "dollar_volume_20d_log", "hl_range_20d", "amihud_20d_log",
    "revision_up", "revision_down", "disclosure_delay_days",
    "atm_iv_30", "iv_term_slope", "iv_put_minus_call_30d",
    "implied_move_1d", "gap_vs_implied", "surprise_vs_implied",
]


# ── forward returns, transcribed (see decision 2) ───────────────────────────


def excess_forward_math(d: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """The forward-excess arithmetic, separated from the file reading so it is
    unit-testable offline against `event_response_v1`'s version.

    Transcribed from `event_response_v1.forward_returns`. The `shift(-1)` is
    the whole point: CRSP daily `ret` is close-to-close, so the event session
    already contains the overnight gap, and a target of `sign(gap) x return`
    that included it would make |gap| contribute positively by construction —
    a guaranteed continuation finding that is pure arithmetic.
    """
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    if "prc" in d:
        d["prc"] = pd.to_numeric(d["prc"], errors="coerce").abs()
    d = d.dropna(subset=["ret"]).sort_values(["permno", "date"])
    mkt = d.groupby("date")["ret"].mean().rename("mkt")
    d = d.merge(mkt, left_on="date", right_index=True, how="left")
    d["ex"] = d["ret"] - d["mkt"]
    for k in horizons:
        inc = (d.groupby("permno")["ex"]
               .transform(lambda s, k=k: s[::-1].rolling(k, min_periods=k)
                          .sum()[::-1]))
        d[f"_inc{k}"] = inc
        d[f"fwd{k}"] = d.groupby("permno")[f"_inc{k}"].shift(-1)
        d = d.drop(columns=[f"_inc{k}"])
    return d


def forward_excess(permnos: set, y0: int, y1: int, horizons: list[int]
                   ) -> pd.DataFrame:
    """Per (permno, session) forward excess return, STRICTLY AFTER the session."""
    frames = []
    for yr in range(y0, y1 + 2):
        p = WRDS / f"crsp_dsf_{yr}.parquet"
        if p.exists():
            f = pd.read_parquet(p, columns=["permno", "date", "ret", "prc"])
            frames.append(f[f["permno"].isin(permnos)])
    if not frames:
        sys.exit("REFUSED: no crsp_dsf_*.parquet covering the corpus window")
    d = excess_forward_math(pd.concat(frames, ignore_index=True), horizons)
    return d[["permno", "date", "prc"] + [f"fwd{k}" for k in horizons]]


# ── the revision target ─────────────────────────────────────────────────────


def load_consensus(permnos: set) -> pd.DataFrame:
    """IBES monthly consensus, FY1 EPS, for the event universe only."""
    frames = []
    for name in ("ibes_consensus_monthly_early", "ibes_consensus_monthly"):
        p = WRDS / f"{name}.parquet"
        if not p.exists():
            continue
        cols = ["permno", "statpers", "measure", "fpi", "meanest", "stdev",
                "numest", "numup", "numdown", "fpedats"]
        f = pd.read_parquet(p, columns=cols)
        f = f[(f["measure"] == FROZEN["measure"])
              & (f["fpi"].astype(str) == FROZEN["fpi"])
              & (f["permno"].isin(permnos))]
        frames.append(f)
    if not frames:
        sys.exit("REFUSED: no IBES consensus parquet found")
    d = pd.concat(frames, ignore_index=True)
    d["statpers"] = pd.to_datetime(d["statpers"])
    d["fpedats"] = pd.to_datetime(d["fpedats"])
    for c in ("meanest", "stdev", "numest", "numup", "numdown"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return (d.dropna(subset=["permno", "statpers", "meanest", "fpedats"])
             .sort_values(["permno", "statpers"])
             .reset_index(drop=True))


def attach_revision(ev: pd.DataFrame, cons: pd.DataFrame) -> pd.DataFrame:
    """The consensus BEFORE the event and the first one at least 5 days after.

    Both cuts must describe the SAME fiscal period (`fpedats`), or the
    difference is a period roll rather than a revision — see decision 3.
    """
    e = ev[["event_id", "permno", "event_date"]].dropna().copy()
    e["permno"] = e["permno"].astype("int64")
    e = e.sort_values("event_date")
    c = cons.copy()
    c["permno"] = c["permno"].astype("int64")

    pre = pd.merge_asof(
        e, c.sort_values("statpers"), left_on="event_date", right_on="statpers",
        by="permno", direction="backward", allow_exact_matches=False,
        suffixes=("", "_t0"))
    pre = pre.rename(columns={
        "statpers": "t0", "meanest": "meanest_t0", "stdev": "stdev_t0",
        "numest": "numest_t0", "numup": "numup_t0", "numdown": "numdown_t0",
        "fpedats": "fpedats_t0"})

    e2 = e.copy()
    e2["cut_from"] = e2["event_date"] + pd.Timedelta(
        days=FROZEN["t1_min_days_after_event"])
    e2 = e2.sort_values("cut_from")
    post = pd.merge_asof(
        e2, c.sort_values("statpers"), left_on="cut_from", right_on="statpers",
        by="permno", direction="forward", allow_exact_matches=True)
    post = post.rename(columns={
        "statpers": "t1", "meanest": "meanest_t1", "stdev": "stdev_t1",
        "numest": "numest_t1", "numup": "numup_t1", "numdown": "numdown_t1",
        "fpedats": "fpedats_t1"})

    j = (pre[["event_id", "t0", "meanest_t0", "stdev_t0", "numest_t0",
              "fpedats_t0"]]
         .merge(post[["event_id", "t1", "meanest_t1", "stdev_t1", "numest_t1",
                      "numup_t1", "numdown_t1", "fpedats_t1"]],
                on="event_id", how="inner"))
    j = j.merge(e[["event_id", "event_date"]], on="event_id", how="left")

    j["t1_lag_days"] = (j["t1"] - j["event_date"]).dt.days
    j = j[j["t1_lag_days"] <= FROZEN["t1_max_days_after_event"]]
    j = j[j["fpedats_t0"] == j["fpedats_t1"]]          # decision 3
    return j


# ── run ─────────────────────────────────────────────────────────────────────


def _fit(model: str, Xtr, ytr, Xte):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if model == "ridge":
        pipe = make_pipeline(SimpleImputer(strategy="median"),
                             StandardScaler(), Ridge(alpha=1.0))
        pipe.fit(Xtr, ytr)
        return pipe.predict(Xte)
    import lightgbm as lgb
    m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05,
                          num_leaves=31, min_child_samples=50,
                          subsample=0.8, colsample_bytree=0.8,
                          random_state=7, verbose=-1)
    m.fit(Xtr, ytr)
    return m.predict(Xte)


def monthly_ic(df: pd.DataFrame, score: str, target: str) -> pd.Series:
    from scipy import stats

    out = {}
    for m, g in df.groupby("event_month"):
        g = g[[score, target]].dropna()
        if len(g) < 10:
            continue
        r = stats.spearmanr(g[score], g[target]).statistic
        if np.isfinite(r):
            out[m] = float(r)
    return pd.Series(out).sort_index()


def summarise(ic: pd.Series) -> dict:
    n = int(len(ic))
    if n < 2:
        return {"n_blocks": n, "mean_ic": None}
    mean = float(ic.mean())
    se = float(ic.std(ddof=1) / np.sqrt(n))
    from scipy import stats
    t = mean / se if se else float("nan")
    p = float(2 * (1 - stats.t.cdf(abs(t), n - 1))) if se else float("nan")
    return {"n_blocks": n, "mean_ic": round(mean, 5), "se": round(se, 5),
            "t": round(float(t), 3), "p": round(p, 5),
            "mde80": round(2.802 * se, 5),
            "under_own_mde80": bool(abs(mean) < 2.802 * se)}


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    order = np.argsort(pvals)
    m = len(pvals)
    passed = np.zeros(m, dtype=bool)
    thresh = q * (np.arange(1, m + 1) / m)
    ok = np.asarray(pvals)[order] <= thresh
    if ok.any():
        passed[order[: int(np.max(np.nonzero(ok)[0])) + 1]] = True
    return passed.tolist()


def build_frame() -> pd.DataFrame:
    """Event features + the revision target + forward excess returns."""
    if not PANEL.exists():
        sys.exit(f"REFUSED: no cached event panel at {PANEL}. Build it with "
                 f"scripts.event_response_v2.build_frame().")
    ev = pd.read_parquet(PANEL)
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    ev = ev[ev["n_estimates"] >= FROZEN["min_estimates"]]
    permnos = set(ev["permno"].dropna().astype("int64"))
    y0 = int(ev["event_date"].dt.year.min())
    y1 = int(ev["event_date"].dt.year.max())

    horizons = [FROZEN["reported_horizon_sessions"],
                FROZEN["primary_horizon_sessions"]]
    px = forward_excess(permnos, y0, y1, horizons)

    ev["permno"] = ev["permno"].astype("int64")
    j = ev.merge(px, left_on=["permno", "event_date"],
                 right_on=["permno", "date"], how="left",
                 suffixes=("", "_px"))

    sign = np.sign(pd.to_numeric(j["overnight_gap"], errors="coerce")).replace(
        0, np.nan)
    for k in horizons:
        j[f"drift{k}"] = sign * j[f"fwd{k}"]

    rev = attach_revision(j, load_consensus(permnos))
    j = j.merge(rev, on="event_id", how="inner", suffixes=("", "_rev"))

    # THE TARGET. Scaled by price (decision: see FROZEN["scaling"]) because an
    # EPS-scaled revision blows up wherever the estimate is near zero, and a
    # price-scaled one is the standard forward-earnings-yield revision and is
    # comparable across names.
    price = pd.to_numeric(j["prc"], errors="coerce").abs()
    j["price_at_event"] = price
    raw = (j["meanest_t1"] - j["meanest_t0"]) / price.replace(0, np.nan)
    j["revision_raw"] = raw.clip(-0.5, 0.5)
    j["revision_signed"] = sign * j["revision_raw"]        # decision 1
    j["d_dispersion"] = (j["stdev_t1"] - j["stdev_t0"]) / price.replace(0, np.nan)
    j["revision_ratio_t1"] = ((j["numup_t1"] - j["numdown_t1"])
                              / j["numest_t1"].replace(0, np.nan))
    return j


def q1_after_t1(fr: pd.DataFrame) -> dict:
    """The premise test, timed correctly: returns measured from the first
    session AFTER the revision is observed.

    Also decomposes the realised revision, within each event month, into the
    part a public numeric surprise explains and the residual. That split is the
    diagnostic that says WHERE any information would have to live -- it is not
    a tradable signal, because the residual is not knowable at the event either.
    """
    from scipy import stats

    permnos = set(fr["permno"].astype("int64"))
    y0 = int(fr["event_date"].dt.year.min())
    y1 = int(fr["event_date"].dt.year.max())
    horizons = [FROZEN["reported_horizon_sessions"],
                FROZEN["primary_horizon_sessions"]]
    px = forward_excess(permnos, y0, y1, horizons).sort_values("date")

    e = fr[["event_id", "permno", "t1", "event_month", "revision_raw",
            "numeric_surprise_pct"]].dropna(subset=["t1"]).copy()
    e["permno"] = e["permno"].astype("int64")
    j = pd.merge_asof(e.sort_values("t1"), px, left_on="t1", right_on="date",
                      by="permno", direction="forward",
                      allow_exact_matches=True)
    # A t1 with no session within a week means the name stopped trading.
    j = j[(j["date"] - j["t1"]).dt.days.between(0, 7)]
    j["yr"] = j["t1"].dt.year
    te = j[j["yr"] >= FROZEN["first_test_year"]].copy()

    rows = []
    for _, g in te.groupby("event_month"):
        g = g.dropna(subset=["revision_raw", "numeric_surprise_pct"]).copy()
        if len(g) < 20:
            continue
        x = stats.rankdata(g["numeric_surprise_pct"])
        y = stats.rankdata(g["revision_raw"])
        x = (x - x.mean()) / x.std()
        y = (y - y.mean()) / y.std()
        b = float((x * y).mean())
        g["rev_explained"] = b * x
        g["rev_residual"] = y - b * x
        rows.append(g)
    if not rows:
        return {"status": "NO_MONTHS"}
    D = pd.concat(rows)

    out = {"n_events": int(len(D)),
           "t1_lag_days_median": float(fr["t1_lag_days"].median())}
    for k in horizons:
        cell = {}
        for name, col in (("revision_raw", "revision_raw"),
                          ("explained_by_surprise", "rev_explained"),
                          ("surprise_orthogonal_residual", "rev_residual")):
            cell[name] = summarise(monthly_ic(D, col, f"fwd{k}"))
        out[f"fwd{k}"] = cell
    return out


def run() -> dict:
    from backend.services import feature_leakage_guard as leak

    OUT.mkdir(parents=True, exist_ok=True)
    fr = build_frame()

    primary = FROZEN["primary_horizon_sessions"]
    reported = FROZEN["reported_horizon_sessions"]
    need = [f"drift{primary}", f"drift{reported}", "revision_signed"]
    fr = fr.dropna(subset=need)
    fr["yr"] = fr["event_date"].dt.year

    coverage = {
        "events_with_a_matched_revision": int(len(fr)),
        "event_months": int(fr["event_month"].nunique()),
        "t1_lag_days_median": float(fr["t1_lag_days"].median()),
        "first_year": int(fr["yr"].min()), "last_year": int(fr["yr"].max()),
    }

    # ── the leakage guard, BEFORE anything is fitted ────────────────────────
    guard = {}
    for tgt in ("revision_signed", f"drift{primary}"):
        rep = leak.assert_no_target_leakage(
            fr[FEATURES + [tgt, "event_month"]], features=FEATURES,
            target=tgt, block="event_month")
        guard[tgt] = rep

    # ── walk-forward ───────────────────────────────────────────────────────
    years = sorted(y for y in fr["yr"].unique()
                   if y >= FROZEN["first_test_year"])
    preds = []
    for y in years:
        tr = fr[fr["yr"] < y]
        te = fr[fr["yr"] == y]
        if len(tr) < 500 or te.empty:
            continue
        Xtr, Xte = tr[FEATURES], te[FEATURES]
        block = te[["event_id", "event_month", f"drift{primary}",
                    f"drift{reported}", "revision_signed",
                    "revision_raw"]].copy()
        for model in FROZEN["models"]:
            for route, tgt in (("direct", f"drift{primary}"),
                               ("routed", "revision_signed")):
                block[f"{model}__{route}"] = _fit(model, Xtr, tr[tgt], Xte)
            # the reported horizon's DIRECT arm needs its own fit; the routed
            # arm is horizon-agnostic (it predicts the mediator), so it is the
            # same column evaluated against a different outcome.
            block[f"{model}__direct_h{reported}"] = _fit(
                model, Xtr, tr[f"drift{reported}"], Xte)
        preds.append(block)

    if not preds:
        sys.exit("REFUSED: no test year had enough training data")
    P = pd.concat(preds, ignore_index=True)

    # ── Q1: does the REALISED revision rank SUBSEQUENT returns? ────────────
    #
    # SUBSEQUENT TO THE REVISION, not to the event. The first implementation of
    # this precondition measured returns from the EVENT, and `t1` sits a median
    # of 20 calendar days after the event -- inside both the 5- and 21-session
    # windows. So the revision was being scored against a return that had
    # already happened when it was observed, and analysts and the market were
    # responding to the same news over overlapping windows.
    #
    # That contaminated version returned IC +0.0454 (t 3.56) at h5 and, for the
    # surprise-orthogonal residual, +0.0504 (t 4.04). Both vanish when the
    # return starts after `t1`. It is recorded here because a t of 4.0 is
    # exactly the number nobody re-examines.
    q1 = {"contaminated_from_event_DO_NOT_CITE": {
        f"drift{k}": summarise(monthly_ic(P, "revision_signed", f"drift{k}"))
        for k in (primary, reported)}}
    q1["from_t1"] = q1_after_t1(fr)

    # ── Q2: is the revision predictable? (precondition) ────────────────────
    q2 = {m: summarise(monthly_ic(P, f"{m}__routed", "revision_signed"))
          for m in FROZEN["models"]}

    # ── Q3: routed vs direct, on RETURNS (the deciding question) ───────────
    arms, pvals, keys = {}, [], []
    for k in (primary, reported):
        for m in FROZEN["models"]:
            direct_col = (f"{m}__direct" if k == primary
                          else f"{m}__direct_h{reported}")
            for route, col in (("direct", direct_col), ("routed", f"{m}__routed")):
                key = f"{m}__{route}__h{k}"
                st = summarise(monthly_ic(P, col, f"drift{k}"))
                arms[key] = st
                if st.get("p") is not None:
                    pvals.append(st["p"])
                    keys.append(key)
    passed = bh_fdr(pvals, q=0.10)
    for key, ok in zip(keys, passed):
        arms[key]["bh_fdr_q10"] = bool(ok)

    paired = {}
    for k in (primary, reported):
        for m in FROZEN["models"]:
            direct_col = (f"{m}__direct" if k == primary
                          else f"{m}__direct_h{reported}")
            a = monthly_ic(P, f"{m}__routed", f"drift{k}")
            b = monthly_ic(P, direct_col, f"drift{k}")
            common = a.index.intersection(b.index)
            d = (a.loc[common] - b.loc[common])
            n = len(d)
            se = float(d.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
            rho = (float(np.corrcoef(a.loc[common], b.loc[common])[0, 1])
                   if n > 2 else float("nan"))
            mean = float(d.mean()) if n else float("nan")
            mde = 2.802 * se if np.isfinite(se) else float("nan")
            band = ("STOP" if not np.isfinite(mean) or mean <= se
                    else "BUILD_AND_WATCH_FORWARD" if mean <= mde
                    else "BUILD")
            paired[f"{m}__h{k}"] = {
                "n_blocks": n, "mean_diff": round(mean, 5),
                "paired_se": round(se, 5), "t": round(mean / se, 3) if se else None,
                "realised_arm_correlation": round(rho, 4),
                "paired_mde80": round(mde, 5),
                "exceeds_1_se": bool(np.isfinite(mean) and mean > se),
                "band": band,
            }

    decisive = paired.get(f"lightgbm__h{primary}", {})
    routed_key = f"lightgbm__routed__h{primary}"
    verdict = ("BUILD" if (decisive.get("exceeds_1_se")
                           and arms.get(routed_key, {}).get("bh_fdr_q10"))
               else "STOP")

    receipt = {
        "trial_id": TRIAL_ID,
        "prereg": PREREG,
        "licence": "PRODUCT_EXPERIMENT (screen — licenses BUILDING, never a claim)",
        "frozen": FROZEN,
        "implementation_decisions_not_in_the_prereg": {
            "sign_convention": ("routed target is sign(gap) x revision, so it "
                                "shares the evaluation target's convention. "
                                "Forced by comparability, declared before "
                                "running. Raw variant reported."),
            "forward_returns": ("computed here rather than by mutating v1's "
                                "frozen SPEC; equivalence to v1's fwd5 is a "
                                "test"),
            "fpedats_match": "t0 and t1 must describe the same fiscal period",
        },
        "coverage": coverage,
        "leakage_guard": guard,
        "Q1_realised_revision_ranks_returns": q1,
        "Q2_revision_is_predictable": q2,
        "Q3_arms": arms,
        "Q3_paired_routed_minus_direct": paired,
        "decisive_cell": f"lightgbm__h{primary}",
        "verdict": verdict,
        "equivalence_note": (
            "a STOP here bounds the effect, it does not refute the "
            "decomposition: the design's paired MDE80 is reported per cell and "
            "the pre-registration declares that a +0.010 difference is NOT "
            "resolvable by this sample."),
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=1),
                                      encoding="utf-8")
    P.to_parquet(OUT / "predictions.parquet")
    return receipt


def main() -> None:
    r = run()
    c = r["coverage"]
    print(f"events with a matched revision {c['events_with_a_matched_revision']}"
          f"  months {c['event_months']}  t1 lag median "
          f"{c['t1_lag_days_median']:.0f}d")
    print()
    print("Q1  realised revision -> returns measured AFTER t1 (PRECONDITION)")
    q1 = r["Q1_realised_revision_ranks_returns"]["from_t1"]
    print(f"   n {q1['n_events']}  t1 lag median {q1['t1_lag_days_median']:.0f}d")
    for hk in [x for x in q1 if x.startswith("fwd")]:
        print(f"   -- {hk}")
        for name, v in q1[hk].items():
            flag = " UNDER-POWERED" if v.get("under_own_mde80") else ""
            print(f"      {name:32s} IC {v['mean_ic']:+.5f}  t {v['t']:+.2f}  "
                  f"MDE80 {v['mde80']:.5f}{flag}")
    bad = r["Q1_realised_revision_ranks_returns"][
        "contaminated_from_event_DO_NOT_CITE"]
    key = f"drift{FROZEN['reported_horizon_sessions']}"
    print(f"   (the contaminated from-event version, kept as a warning: "
          f"{key} IC {bad[key]['mean_ic']:+.5f} t {bad[key]['t']:+.2f})")
    print()
    print("Q2  event state -> revision (PRECONDITION)")
    for k, v in r["Q2_revision_is_predictable"].items():
        print(f"   {k:10s} IC {v['mean_ic']:+.5f}  t {v['t']:+.2f}  "
              f"MDE80 {v['mde80']:.5f}")
    print()
    print("Q3  arms vs RETURNS")
    for k, v in r["Q3_arms"].items():
        print(f"   {k:34s} IC {v['mean_ic']:+.5f}  t {v['t']:+.2f}  "
              f"BH-FDR {'PASS' if v.get('bh_fdr_q10') else 'no'}")
    print()
    print("Q3  paired  routed - direct")
    for k, v in r["Q3_paired_routed_minus_direct"].items():
        print(f"   {k:22s} {v['mean_diff']:+.5f} +- {v['paired_se']:.5f}  "
              f"rho {v['realised_arm_correlation']:+.3f}  "
              f"MDE80 {v['paired_mde80']:.5f}  {v['band']}")
    print()
    print("VERDICT", r["verdict"])


if __name__ == "__main__":
    main()
