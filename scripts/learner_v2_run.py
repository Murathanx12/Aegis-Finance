"""AEGIS LEARNER v2 -- a shared multi-horizon encoder, priced at every horizon,
and the calibration numbers v1 never produced.

    python -m scripts.learner_v2_run                # the full run
    python -m scripts.learner_v2_run --smoke        # 2 test years, plumbing only
    python -m scripts.learner_v2_run --horizons 1   # one horizon

WHAT v2 ADDS TO v1, AND WHAT IT DELIBERATELY DOES NOT TOUCH
===========================================================
v1 (`scripts/learner_run.py`, receipt `learner_v1.json`) stands untouched and
reproducible. Its training table, its prior, its baselines and its arms are
imported, not reimplemented, and this script writes a DIFFERENT receipt. The
one number v2 recomputes from v1's own sealed OOS predictions is v1's champion
book, as a reproduction check printed in the receipt.

Four things are new:

1. **A shared encoder with per-horizon heads** (`learner/encoder.py`). One
   trunk, eight heads (expected excess and P(excess > 0) at 1/3/6/12m), fitted
   once per test year instead of eight times.

2. **Money at every horizon.** v1 graded 3m/6m/12m on rank IC alone -- so the
   single most striking number in it (the engine prior's IC t rising to **34.5
   at 12m**) had no price attached, and "is the 12m horizon where the edge
   lives?" could not be answered. `evaluate.overlapping_book` prices a
   monthly-formed, h-month-held book.

3. **Calibration** (`learner/calibrate.py`). v1's champion emits a probability
   and v1 scored not one Brier point, which is why the 2026-09-02 shadow book's
   `P(beat) = 0.494` had no reading on disk.

4. **Paired comparison against v1's champion**, month by month. "Did v2 beat
   v1?" answered on 107 paired draws rather than by putting two terminal
   wealths next to each other, which is one draw of a correlated pair.

LICENCE: PRODUCT_EXPERIMENT. Explore dirty, promote clean. What does not relax
and is enforced in code: no information acted on before it was public (splits
by DATE, per-horizon maturity masks); no target leakage; costs never zero
(10bps/side on measured turnover, gross printed beside net); a candidate that
enters forward paper is frozen. This script places NOTHING and imports no
broker; `backend/tests/test_learner_pit.py` asserts that over the AST.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import baselines as B                          # noqa: E402
from learner import calibrate as C                          # noqa: E402
from learner import dataset as D                            # noqa: E402
from learner import encoder as EN                           # noqa: E402
from learner import evaluate as E                           # noqa: E402
from learner import models as M                             # noqa: E402
from learner import prior as P                              # noqa: E402

RECEIPT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "learner_v2_20260903.json"
V1_RECEIPT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "learner_v1.json"
PRED_DIR = REPO / "backend" / "data" / "optimus" / "learner"

TEST_YEARS = tuple(range(2016, 2025))
HORIZONS = (1, 3, 6, 12)
BOOK_K = 50
RANDOM_SEED = 20260903

#: v1's champion at the 1m horizon -- the incumbent v2 has to beat.
V1_CHAMPION = "lgbm_clf"

NULL_LGBM = "NULL_shuffled__lgbm_raw"
NULL_ENC = "NULL_shuffled__encoder_raw"

#: arms whose output is a PROBABILITY and therefore has a calibration answer
PROBABILITY_ARMS = ("lgbm_clf", "encoder_clf__raw", "encoder_clf__residual")
#: arms that emit a percentile, not a return -- never put through a decile table
RANK_ONLY = ("rank_upside", "rank_consensus", "random_rank")


# --------------------------------------------------------- the prereg header

def prereg_header(horizons, test_years) -> dict:
    """Written to disk BEFORE the first fit, and appended to afterwards."""
    return {
        "artefact": "AEGIS_LEARNER_v2",
        "licence": "PRODUCT_EXPERIMENT",
        "builds_on": "AEGIS_LEARNER_v1 (backend/data/optimus/tracker_backtest/learner_v1.json)",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "written_before": "any v2 model was fitted; every table below was appended after",
        "v1_result_being_extended": {
            "champion": "lgbm_clf, rank IC 0.0954 (t 8.21) on 107 OOS months",
            "the_gap": "paired money t was only 1.49 over 12 arms; the ML added ~zero "
                       "inside the engine's 3-5 band and earned its highest IC (0.137) at "
                       "`no_opinion`; the engine prior's own IC t rises to 34.5 at 12m.",
            "what_v1_never_measured": [
                "any money number at 3/6/12m -- IC only, so the horizon question was open",
                "any calibration number at all, for a champion that emits a probability",
                "any paired test BETWEEN arms -- only each arm against the market",
            ],
        },
        "hypotheses": {
            "V2-H1": "a SHARED encoder trained on all four horizons at once beats a "
                     "1m-only model on the 1m cross-section -- i.e. the 12m target, which "
                     "is the least noisy, teaches a representation the 1m head can use.",
            "V2-H2": "the money follows the IC across horizons: if the prior's IC t rises "
                     "12.7 -> 34.5 from 1m to 12m, a 12m-held book should show a larger and "
                     "more significant paired excess than a 1m book.",
            "V2-H3": "the classifier's P(excess > 0) is a RANKING SCORE, not a literal "
                     "probability: its reliability bins will sit off the diagonal and "
                     "temporal recalibration will move Brier materially.",
            "V2-H4": "the ENGINE-RESIDUAL form beats the RAW form for the encoder, for the "
                     "same reason v1 tested it -- handing the model the prior as an offset "
                     "rather than as a feature.",
        },
        "honest_prior_before_running": (
            "V2-H1: probably NO. v1's four model families landed within 0.07-0.10 IC of "
            "each other on the same features, which is the signature of a feature ceiling, "
            "not an architecture ceiling. A shared trunk cannot manufacture information. "
            "V2-H2: likely YES on IC and UNCERTAIN on money -- a longer hold pays less "
            "turnover, but the 1m book's turnover was already only 0.88 and its cost drag "
            "about 2.1%/yr, so the horizon gain has to come from the signal, not the cost. "
            "V2-H3: expect the LEVEL to be biased and the ORDER to be fine -- T13's "
            "'the model orders better than it prices' is the house's most repeated "
            "calibration finding. V2-H4: no difference; v1's raw arm was ahead by a "
            "hair (8.354 vs 8.233) which is noise."),
        "primary_decision_metric": (
            "terminal wealth of a monthly-formed top-50 value-weighted book NET of 10bps "
            "per side on measured turnover, per horizon (h-month hold via the overlapping "
            "construction for h > 1), over the walk-forward OOS years "
            f"{test_years[0]}-{test_years[-1]}."),
        "secondary_decision_metrics": [
            "paired monthly excess vs the VW market, t across MONTHS (the date-block n)",
            "max drawdown of the compounded net path, and 5% CVaR of monthly returns",
            "Brier / log loss / ECE / reliability slope for every probability arm",
        ],
        "ic_is_diagnostic_only": (
            "rank IC is reported for every arm and DECIDES NOTHING. v1 is the reason: its "
            "champion had IC t 8.21 and money t 1.49, and ranking on IC would have "
            "promoted a book that does not compound."),
        "decision_rule_declared_in_advance": {
            "champion_per_horizon": (
                "highest net terminal wealth among arms clearing BOTH (i) paired-vs-market "
                "t >= 1.0 with positive annualised excess and (ii) rank IC t >= 2.0. If "
                "nothing clears, the champion is `prior` and `ml_earned_the_seat` = false."),
            "beats_v1": (
                "an arm BEATS v1 only if the PAIRED MONTHLY DIFFERENCE of its net book "
                "series minus v1's champion (`" + V1_CHAMPION + "`, same months, same "
                "construction) has a positive mean AND t >= 1.0. Two terminal wealths "
                "side by side are ONE draw of a correlated pair and settle nothing."),
            "v2_h3_calibration": (
                "the probability is called LITERAL only if ECE <= 0.02 AND the reliability "
                "slope is in [0.5, 1.5] AND temporal recalibration improves Brier by less "
                "than 1%. Otherwise it is a ranking score with a decimal point."),
        },
        "null_controls": {
            NULL_LGBM: "v1's null, re-run per horizon: the same LightGBM pipeline with the "
                       "training target permuted WITHIN each month.",
            NULL_ENC: "the same permutation through the ENCODER, so the multi-horizon "
                      "architecture gets its own leak test rather than inheriting one. The "
                      "return and its 0/1 label are permuted TOGETHER, or the two heads "
                      "would be trained against different nulls.",
            "expected": "IC ~ 0, |t| < 2, no book edge. If a null scores, every number in "
                        "this receipt is void and the receipt says so.",
        },
        "known_flattery_of_the_incumbent": (
            "BAND_PRIOR v2's constants were fitted on the FULL 2013-2024 window, so the "
            "`prior` baseline knows the test years and no ML arm does. Carried forward "
            "from v1 unchanged."),
        "one_preprocessing_change_from_v1": (
            "the encoder clips standardised features at +/-5 sd. Without it the regression "
            "heads returned an sd of 15.3 in excess-return units. v1's MLP has no clip, so "
            "`encoder vs v1 MLP` is architecture PLUS clip, not architecture alone."),
        "walk_forward": {
            "test_years": list(test_years),
            "horizons_months": list(horizons),
            "train_rule_single_horizon": "v1's: every row whose target had MATURED before "
                                         "1 Jan of the test year.",
            "train_rule_multi_horizon": "a row is admitted if ANY horizon has matured; each "
                                        "horizon's target is then MASKED unless its own "
                                        "mat_date is before the cutoff. A masked target "
                                        "contributes zero gradient.",
            "splits": "expanding window, by DATE only. Never random k-fold.",
        },
        "broker_authority": "NONE. This script writes JSON. No order path imports learner/.",
    }


# --------------------------------------------------------------- the arms

def _random_rank(test: pd.DataFrame) -> np.ndarray:
    """A reproducible random ordering -- the ruler v1 did not have.

    `constant` measures what an arbitrary 50 names earn but has no ordering at
    all, so nothing in v1 answered "how much of the champion's book is the
    ORDER, and how much is simply being long 50 large names?". This does: it
    is a real ranking that carries no information. Seeded on (permno, month)
    rather than drawn fresh so a re-run reproduces the same book, and NEVER on
    permno order -- low permnos are the oldest listings, and the farm's
    oldest-listings null beat 13 of 15 real signals.
    """
    mo = test["month"].astype(str).str.replace("-", "", regex=False).astype("int64")
    h = (test["permno"].astype("int64") * 6_364_136_223_846_793_005
         + mo * 1_442_695_040_888_963_407 + RANDOM_SEED)
    h = (h ^ (h >> np.int64(31))) % np.int64(1_000_003)
    return (h.to_numpy(dtype="float64") / 1_000_003.0)


def run_year_arms(df: pd.DataFrame, horizon: int, feature_cols: list[str],
                  test_years, kinds: tuple[str, ...], with_mlp: bool,
                  verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """v1-style per-horizon arms: baselines, ridge/lgbm/mlp x raw/residual, clf, null."""
    preds = pd.DataFrame(index=df.index, dtype="float64")
    fits: dict = {}

    def put(col, idx, vals):
        if col not in preds.columns:
            preds[col] = np.nan
        preds.loc[idx, col] = vals

    for year, tr, te in D.walk_forward_splits(df, test_years, horizon):
        t0 = time.time()
        train, test = df.loc[tr], df.loc[te]
        for name in B.BASELINE_NAMES:
            put(name, te, B.predict(name, train, test, horizon))
        put("random_rank", te, _random_rank(test))
        for kind in kinds:
            if kind == "mlp" and not with_mlp:
                continue
            for arm in M.ARMS:
                p, meta = M.fit_predict(kind, arm, train, test, feature_cols, horizon)
                put(f"{kind}__{arm}", te, p)
                fits.setdefault(f"{kind}__{arm}", {})[str(year)] = {
                    k: v for k, v in meta.items() if k != "feature_cols"}
        p, meta = M.fit_predict_proba(train, test, feature_cols, horizon)
        put(M.CLASSIFIER, te, p)
        fits.setdefault(M.CLASSIFIER, {})[str(year)] = meta
        p, meta = M.fit_predict("lgbm", "raw", train, test, feature_cols, horizon,
                                shuffle_target=True)
        put(NULL_LGBM, te, p)
        fits.setdefault(NULL_LGBM, {})[str(year)] = {
            k: v for k, v in meta.items() if k != "feature_cols"}
        if verbose:
            print(f"      {horizon}m {year}: train {len(tr):,} -> test {len(te):,} "
                  f"({time.time() - t0:.1f}s)")
    return preds, fits


def run_encoder(df: pd.DataFrame, feature_cols: list[str], test_years,
                horizons, verbose: bool = True) -> tuple[dict, dict]:
    """ONE encoder fit per (arm, year) -> predictions for every horizon at once.

    Returns ``{horizon: DataFrame of prediction columns}`` and the fit metadata.
    """
    cols = {h: pd.DataFrame(index=df.index, dtype="float64") for h in horizons}
    fits: dict = {}
    first_year = True
    frozen_cfg: dict | None = None
    for year, tr, te, masks in EN.multi_horizon_splits(df, test_years, horizons):
        train, test = df.loc[tr], df.loc[te]
        for arm in EN.ARMS:
            t0 = time.time()
            enc = EN.MultiHorizonEncoder(arm, feature_cols, horizons=horizons,
                                         cfg=frozen_cfg)
            # The grid is searched ONCE, on the first test year's inner temporal
            # holdout, then frozen. That choice sees only rows matured before
            # the first test year, so it is PIT-clean and costs one grid.
            enc.fit(train, masks, search_grid=(first_year and frozen_cfg is None))
            if frozen_cfg is None:
                frozen_cfg = dict(enc.cfg)
            out = enc.predict(test)
            for h in horizons:
                for head, name in (("reg", f"encoder__{arm}"),
                                   ("clf", f"encoder_clf__{arm}")):
                    if name not in cols[h].columns:
                        cols[h][name] = np.nan
                    cols[h].loc[te, name] = out[(head, h)]
            fits.setdefault(f"encoder__{arm}", {})[str(year)] = enc.meta
            if verbose:
                print(f"      encoder {arm} {year}: train {len(tr):,} "
                      f"({time.time() - t0:.1f}s, {enc.meta['epochs_run']} epochs)")
        # the encoder's own shuffled null
        t0 = time.time()
        null = EN.MultiHorizonEncoder("raw", feature_cols, horizons=horizons,
                                      cfg=frozen_cfg)
        null.fit(train, masks, search_grid=False, shuffle_target=True)
        out = null.predict(test)
        for h in horizons:
            if NULL_ENC not in cols[h].columns:
                cols[h][NULL_ENC] = np.nan
            cols[h].loc[te, NULL_ENC] = out[("reg", h)]
        fits.setdefault(NULL_ENC, {})[str(year)] = null.meta
        if verbose:
            print(f"      encoder NULL {year}: ({time.time() - t0:.1f}s)")
        first_year = False
    return cols, fits


# ------------------------------------------------------------------ grading

def grade_horizon(df: pd.DataFrame, preds: pd.DataFrame, horizon: int,
                  full_bands: bool = True) -> tuple[dict, dict]:
    """Every arm at one horizon. Returns (scoreboard, {arm: net monthly series})."""
    scored = df.join(preds, rsuffix="_pred")
    y = f"excess_vw_{horizon}m"
    scored = scored[scored[y].notna()]
    out: dict = {}
    series: dict = {}
    for col in preds.columns:
        sub = scored[scored[col].notna()]
        if sub.empty:
            continue
        calibrated = col not in RANK_ONLY and col not in PROBABILITY_ARMS
        row: dict = {"rank_ic": E.rank_ic(sub, col, y)}
        if calibrated:
            tab = E.decile_table(sub, col, y)
            row["decile_table"] = tab
            row["calibration_slope_of_the_level"] = E.calibration_slope(tab)
        else:
            row["calibration_slope_of_the_level"] = {
                "note": "output is a percentile or a probability, not a return -- a decile "
                        "table would compare two different units"}
        row["top_minus_bottom_decile"] = E.top_minus_bottom(sub, col, y)
        if horizon == 1:
            bk = E.book(sub, col, k=BOOK_K, weight="vw", with_risk=True, return_series=True)
        else:
            bk = E.overlapping_book(sub, col, horizon, k=BOOK_K, weight="vw",
                                    with_risk=True, return_series=True)
        s = bk.pop("_series", None)
        if s is not None:
            series[col] = s
        row["book_top50_vw"] = bk
        if full_bands:
            row["by_band"] = E.grade_by_band(sub, col, horizon)
        if horizon == 1:
            row["by_era"] = E.grade_by_era(sub, col, horizon)
        out[col] = row
    return out, series


def calibration_for(df: pd.DataFrame, preds: pd.DataFrame, horizon: int) -> dict:
    """Brier / log loss / reliability / temporal Platt + isotonic, per prob arm."""
    lab = f"pos_vw_{horizon}m"
    scored = df.join(preds, rsuffix="_pred")
    scored = scored[scored[lab].notna()]
    out: dict = {
        "label": lab,
        "unconditional_base_rate_on_these_rows": round(float(scored[lab].mean()), 5),
        "why_the_base_rate_and_not_0_5": (
            "individual-stock excess returns are right-skewed, so most names lose to a "
            "cap-weighted market most months. Reading a score of 0.49 against 0.5 is "
            "reading it against the wrong number."),
    }
    for col in PROBABILITY_ARMS:
        if col not in preds.columns:
            continue
        sub = scored[scored[col].notna()]
        if len(sub) < 5000:
            out[col] = {"note": f"only {len(sub)} rows"}
            continue
        out[col] = C.calibration_report(sub[lab].to_numpy(), sub[col].to_numpy(),
                                        sub["month"].to_numpy())
    return out


def choose_champion(scoreboard: dict) -> dict:
    """The bar declared in the header, applied mechanically."""
    qualifying = []
    for name, row in scoreboard.items():
        if name.startswith("NULL_"):
            continue                       # a null is a check, never a candidate
        bk = row.get("book_top50_vw") or {}
        ic_t = (row.get("rank_ic") or {}).get("t_stat")
        pair_t = bk.get("t_stat_paired_vs_market")
        exc = bk.get("annualised_excess")
        tw = bk.get("terminal_wealth_net")
        if (ic_t is not None and ic_t >= 2.0 and pair_t is not None and pair_t >= 1.0
                and exc is not None and exc > 0 and tw is not None):
            qualifying.append((tw, name))
    if not qualifying:
        return {"champion": "prior", "ml_earned_the_seat": False,
                "reason": "no arm cleared the pre-declared bar (rank IC t >= 2.0 AND "
                          "paired-vs-market t >= 1.0 AND positive annualised excess)"}
    qualifying.sort(reverse=True)
    tw, name = qualifying[0]
    return {"champion": name,
            "ml_earned_the_seat": name not in B.BASELINE_NAMES and name != "random_rank",
            "terminal_wealth_net": tw,
            "qualifying_arms": [n for _, n in qualifying],
            "reason": "highest OOS net terminal wealth among arms clearing the bar"}


def beats_v1(series: dict, scoreboard: dict, incumbent: str) -> dict:
    """The PAIRED test. Two terminal wealths side by side settle nothing."""
    if incumbent not in series:
        return {"note": f"{incumbent} produced no book -- CANNOT DETERMINE"}
    base = series[incumbent]["net"]
    out: dict = {"incumbent": incumbent,
                 "rule": "positive mean monthly difference AND paired t >= 1.0",
                 "arms": {}}
    winners = []
    for name, s in series.items():
        if name == incumbent:
            continue
        d = E.paired_difference(s["net"], base, name, incumbent)
        bk = scoreboard.get(name, {}).get("book_top50_vw", {})
        d["own_paired_t_vs_market"] = bk.get("t_stat_paired_vs_market")
        d["own_annualised_excess"] = bk.get("annualised_excess")
        t = d.get("t_stat_paired")
        d["beats_incumbent"] = bool(
            t is not None and t >= 1.0 and (d.get("mean_monthly_difference") or 0) > 0)
        out["arms"][name] = d
        if d["beats_incumbent"]:
            winners.append(name)
    out["arms_beating_the_incumbent"] = winners
    out["verdict"] = ("BEATEN by " + ", ".join(winners)) if winners else (
        "NOT BEATEN -- no arm's paired monthly difference against the incumbent cleared "
        "t >= 1.0 with a positive mean")
    return out


def tradable_variant(df: pd.DataFrame, preds: pd.DataFrame, horizon: int,
                     arm: str) -> dict:
    """The champion's book again, with the $3m/day execution floor applied."""
    if arm not in preds.columns:
        return {"note": f"{arm} has no prediction column -- CANNOT DETERMINE"}
    y = f"excess_vw_{horizon}m"
    sub = df.join(preds[[arm]], rsuffix="_pred")
    sub = sub[sub[y].notna() & sub[arm].notna()]
    if sub.empty:
        return {"note": "no rows"}
    if horizon == 1:
        bk = E.book(sub, arm, k=BOOK_K, weight="vw",
                    tradable_floor=E.TRADABLE_DOLLAR_VOL, with_risk=True)
    else:
        bk = E.overlapping_book(sub, arm, horizon, k=BOOK_K, weight="vw",
                                tradable_floor=E.TRADABLE_DOLLAR_VOL, with_risk=True)
    bk.pop("_series", None)
    return bk


def residual_vs_raw(series: dict) -> dict:
    """V2-H4 as a PAIRED test, month by month, not two terminal wealths."""
    out = {}
    for base in ("encoder", "encoder_clf", "ridge", "lgbm"):
        a, b = f"{base}__residual", f"{base}__raw"
        if a in series and b in series:
            out[base] = E.paired_difference(series[a]["net"], series[b]["net"], a, b)
    return out


def null_check(scoreboard: dict) -> dict:
    """A null owes two tests. This is the leak test; the era split is the regime one."""
    out = {}
    for name in (NULL_LGBM, NULL_ENC):
        row = scoreboard.get(name)
        if not row:
            continue
        ic = row.get("rank_ic", {})
        bk = row.get("book_top50_vw", {})
        t = ic.get("t_stat")
        out[name] = {
            "rank_ic": ic.get("mean_ic"), "rank_ic_t": t,
            "annualised_excess": bk.get("annualised_excess"),
            "paired_t_vs_market": bk.get("t_stat_paired_vs_market"),
            "flat": bool(t is not None and abs(t) < 2.0),
        }
    out["all_nulls_flat"] = all(v.get("flat") for v in out.values() if isinstance(v, dict))
    out["if_a_null_scores"] = ("every number in this receipt is plumbing rather than "
                               "signal and must be read as void")
    return out


def reproduce_v1(df: pd.DataFrame) -> dict:
    """Recompute v1's champion book from v1's OWN sealed OOS predictions.

    Not a re-fit: it reads `oos_predictions_1m.parquet` and re-runs the grader.
    If v1's recorded book comes back byte-identical, then every v2 number
    computed by the same grader is on the same footing as v1's, and the two
    receipts can be compared at all. If it does not, the comparison is void and
    the receipt says which keys moved.
    """
    path = PRED_DIR / "oos_predictions_1m.parquet"
    if not path.exists() or not V1_RECEIPT.exists():
        return {"status": "CANNOT DETERMINE",
                "reason": f"missing {path.name} or the v1 receipt"}
    pv1 = pd.read_parquet(path)
    if V1_CHAMPION not in pv1.columns:
        return {"status": "CANNOT DETERMINE",
                "reason": f"{V1_CHAMPION} absent from v1's OOS predictions"}
    joined = df.join(pv1[[V1_CHAMPION]].rename(columns={V1_CHAMPION: "_v1"}))
    sub = joined[joined["excess_vw_1m"].notna() & joined["_v1"].notna()]
    got = E.book(sub, "_v1", k=BOOK_K, weight="vw")
    want = (json.loads(V1_RECEIPT.read_text(encoding="utf-8"))
            .get("scoreboard_1m", {}).get(V1_CHAMPION, {}).get("book_top50_vw", {}))
    diffs = {k: {"v1_receipt": want[k], "recomputed": got.get(k)}
             for k in want if got.get(k) != want[k]}
    return {"status": "REPRODUCED" if not diffs else "DIVERGED",
            "arm": V1_CHAMPION,
            "keys_compared": len(want),
            "differences": diffs,
            "meaning": ("v1's grader and v2's grader agree on v1's own sealed predictions, "
                        "so the two receipts are on one footing"
                        if not diffs else
                        "the graders DISAGREE -- every v1-vs-v2 comparison below is void")}


# ------------------------------------------------------------------- the run

def run(horizons=HORIZONS, test_years=TEST_YEARS, smoke: bool = False,
        verbose: bool = True) -> int:
    t_start = time.time()
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)

    receipt: dict = {"prereg_header": prereg_header(horizons, test_years)}
    RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"  prereg header sealed -> {RECEIPT.name}")

    if not EN.torch_available():
        raise SystemExit("REFUSED: torch is absent. The v2 encoder is the experiment; "
                         "silently running v1's arms and calling it v2 would be worse "
                         "than not running.")

    df = D.load()
    print(f"  table: {len(df):,} rows, {df['month'].nunique()} months "
          f"(REUSED -- v2 never rebuilds; dataset.py is v1's)")
    feature_cols = D.feature_columns()
    receipt["dataset"] = {
        "path": str(D.TRAIN_TABLE), "rows": int(len(df)),
        "months": int(df["month"].nunique()), "names": int(df["permno"].nunique()),
        "schema_hash": D.schema_hash(),
        "n_features": len(feature_cols),
        "reused": "built by v1; v2 never rebuilds it and treats dataset.py as read-only",
    }
    receipt["prior"] = P.describe()
    receipt["models_v1"] = M.describe()
    receipt["encoder_v2"] = EN.describe()
    receipt["calibration_method"] = C.describe()
    receipt["baselines"] = B.describe() + [
        {"name": "random_rank", "is_calibrated": False,
         "description": "a reproducible RANDOM ordering, seeded on (permno, month). The "
                        "ruler v1 lacked: it separates 'the order carries information' "
                        "from 'being long 50 large names in a bull decade'."}]
    receipt["evaluation_conventions"] = {
        "cost_bps_per_side": E.COST_BPS_PER_SIDE,
        "cost_basis": "measured weight turnover, both sides; gross reported beside net",
        "t_stat_n": "MONTHS (date blocks), never name-months",
        "book_1m": f"monthly top-{BOOK_K}, value-weighted, ties broken by a SEEDED HASH of "
                   "(permno, month) -- never by permno ascending, which is listing age",
        "book_longer_horizons": "overlapping: a new top-50 cohort every month, held h "
                                "months, portfolio = 1/h in each live cohort",
        "ic_is_diagnostic_only": True,
    }
    receipt["v1_reproduction_check"] = reproduce_v1(df)
    print(f"  v1 reproduction: {receipt['v1_reproduction_check']['status']}")
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")

    # 1. the encoder -- one fit per (arm, year), every horizon at once
    print("  encoder walk-forward (all horizons per fit) ...")
    enc_cols, enc_fits = run_encoder(df, feature_cols, test_years, horizons, verbose)

    # 2. the per-horizon arms, and the grading
    receipt["scoreboards"] = {}
    receipt["calibration"] = {}
    receipt["champions"] = {}
    receipt["vs_v1_paired"] = {}
    receipt["null_controls"] = {}
    receipt["fit_metadata"] = {"encoder": enc_fits}
    all_preds: dict[int, pd.DataFrame] = {}
    series_by_h: dict[int, dict] = {}
    for h in horizons:
        print(f"  horizon {h}m: v1-style arms ...")
        kinds = ("ridge", "lgbm") if smoke else M.LEARNABLE
        preds, fits = run_year_arms(df, h, feature_cols, test_years, kinds,
                                    with_mlp=not smoke, verbose=verbose)
        for c in enc_cols[h].columns:
            preds[c] = enc_cols[h][c]
        all_preds[h] = preds
        receipt["fit_metadata"][f"{h}m"] = fits
        print(f"  horizon {h}m: grading {len(preds.columns)} arms ...")
        sb, series = grade_horizon(df, preds, h)
        series_by_h[h] = series
        receipt["scoreboards"][f"{h}m"] = sb
        receipt["calibration"][f"{h}m"] = calibration_for(df, preds, h)
        champ = choose_champion(sb)
        receipt["champions"][f"{h}m"] = champ
        # The $3m/day execution floor, on the champion only. A book that holds
        # names the house classifies OBSERVE_ONLY is a backtest of something
        # unbuyable, and v1 learned that a floor with no liquidity column
        # silently passes everything -- so it is DERIVED or the run refuses.
        champ["tradable_floor_variant"] = tradable_variant(df, preds, h, champ["champion"])
        receipt["null_controls"][f"{h}m"] = null_check(sb)
        receipt["residual_vs_raw"] = receipt.get("residual_vs_raw", {})
        receipt["residual_vs_raw"][f"{h}m"] = residual_vs_raw(series)
        if h == 1:
            receipt["vs_v1_paired"][f"{h}m"] = beats_v1(series, sb, V1_CHAMPION)
        else:
            # At longer horizons v1 has no book at all, so the incumbent is the
            # ENGINE PRIOR -- the thing that is actually running. Naming it is
            # the point: "better than what?" is answered, not assumed.
            receipt["vs_v1_paired"][f"{h}m"] = beats_v1(series, sb, "prior")
        RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
        print(f"    champion {h}m: {receipt['champions'][f'{h}m']['champion']}")

    # 3. the horizon question, side by side
    receipt["horizon_comparison"] = horizon_table(receipt["scoreboards"])
    receipt["verdicts"] = verdicts(receipt)
    receipt["runtime_seconds"] = round(time.time() - t_start, 1)

    out = PRED_DIR / "oos_predictions_v2.parquet"
    keep = df[["permno", "month", "entry_date"]].copy()
    for h in horizons:
        for c in all_preds[h].columns:
            keep[f"{c}__{h}m"] = all_preds[h][c]
    keep.to_parquet(out, index=False)
    receipt["oos_predictions_path"] = str(out)

    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    _print(receipt)
    print(f"\n  receipt -> {RECEIPT}  ({receipt['runtime_seconds']}s)")
    return 0


def horizon_table(scoreboards: dict) -> dict:
    """V2-H2 in one place: does the money follow the IC across horizons?"""
    rows = {}
    for hk, sb in scoreboards.items():
        for arm, row in sb.items():
            bk = row.get("book_top50_vw", {})
            ic = row.get("rank_ic", {})
            rows.setdefault(arm, {})[hk] = {
                "rank_ic": ic.get("mean_ic"), "rank_ic_t": ic.get("t_stat"),
                "terminal_wealth_net": bk.get("terminal_wealth_net"),
                "terminal_wealth_market": bk.get("terminal_wealth_market_same_months"),
                "annualised_excess": bk.get("annualised_excess"),
                "paired_t_vs_market": bk.get("t_stat_paired_vs_market"),
                "mean_turnover": bk.get("mean_turnover"),
                "max_drawdown_net": (bk.get("risk") or {}).get("max_drawdown_net"),
            }
    return rows


def verdicts(rep: dict) -> dict:
    sbs = rep["scoreboards"]
    out: dict = {}

    # V2-H1: the encoder against v1's own 1m models.
    one = sbs.get("1m", {})

    def tw(arm):
        return (one.get(arm, {}).get("book_top50_vw", {}) or {}).get("terminal_wealth_net")

    enc_best = max([(tw(a) or -np.inf, a) for a in
                    ("encoder__raw", "encoder__residual",
                     "encoder_clf__raw", "encoder_clf__residual")])
    v1_best = max([(tw(a) or -np.inf, a) for a in
                   ("ridge__raw", "ridge__residual", "lgbm__raw", "lgbm__residual",
                    "mlp__raw", "mlp__residual", "lgbm_clf")])
    paired = rep.get("vs_v1_paired", {}).get("1m", {})
    beat = paired.get("arms_beating_the_incumbent", [])
    enc_beat = [a for a in beat if a.startswith("encoder")]
    out["V2-H1_shared_encoder_beats_a_1m_only_model"] = {
        "best_encoder_arm": enc_best[1],
        "best_encoder_terminal_wealth": (None if enc_best[0] == -np.inf else enc_best[0]),
        "best_v1_arm": v1_best[1],
        "best_v1_terminal_wealth": (None if v1_best[0] == -np.inf else v1_best[0]),
        "encoder_arms_beating_v1_champion_on_the_PAIRED_metric": enc_beat,
        "verdict": "SUPPORTED" if enc_beat else "NOT SUPPORTED",
        "note": "the paired metric decides, not the terminal wealths side by side",
    }

    # V2-H2: money vs IC across horizons, for the engine prior and the champions.
    ht = rep.get("horizon_comparison", {})
    prior_row = ht.get("prior", {})
    best_pair = {}
    for hk, sb in sbs.items():
        cand = [((r.get("book_top50_vw") or {}).get("t_stat_paired_vs_market"), a)
                for a, r in sb.items() if not a.startswith("NULL_")]
        cand = [(t, a) for t, a in cand if t is not None]
        best_pair[hk] = (max(cand) if cand else (None, None))
    short, long_ = f"{min(HORIZONS)}m", f"{max(HORIZONS)}m"
    h2_verdict = "CANNOT DETERMINE"
    if short in best_pair and long_ in best_pair and short != long_:
        ts, tl = best_pair[short][0], best_pair[long_][0]
        ps = (prior_row.get(short) or {}).get("annualised_excess")
        pl = (prior_row.get(long_) or {}).get("annualised_excess")
        if None not in (ts, tl):
            h2_verdict = ("SUPPORTED" if tl > ts else "NOT SUPPORTED")
        out["_h2_inputs"] = {"best_paired_t_short": ts, "best_paired_t_long": tl,
                             "prior_annualised_excess_short": ps,
                             "prior_annualised_excess_long": pl}
    out["V2-H2_the_money_follows_the_IC_across_horizons"] = {
        "prior_by_horizon": prior_row,
        "champion_by_horizon": {k: v.get("champion") for k, v in rep["champions"].items()},
        "best_paired_t_by_horizon": {k: {"t": v[0], "arm": v[1]}
                                     for k, v in best_pair.items()},
        "verdict": h2_verdict,
        "rule": f"SUPPORTED if the best paired-vs-market t at {long_} exceeds the best at "
                f"{short}. IC is diagnostic and does not enter this rule.",
    }

    # V2-H3: is the probability literal?
    cal = rep.get("calibration", {})
    h3 = {}
    for hk, block in cal.items():
        for arm in PROBABILITY_ARMS:
            b = block.get(arm)
            if not isinstance(b, dict) or "verdict" not in b:
                continue
            v = b["verdict"]
            imp = v.get("best_brier_improvement_from_temporal_recalibration")
            raw_brier = (b.get("raw_all_rows") or {}).get("brier")
            pct = (100.0 * imp / raw_brier) if (imp is not None and raw_brier) else None
            h3[f"{hk}/{arm}"] = {
                "ece": v.get("ece"), "reliability_slope": v.get("reliability_slope"),
                "brier_skill_score": v.get("brier_skill_score_vs_base_rate"),
                "recalibration_brier_gain_pct": (round(pct, 3) if pct is not None else None),
                "base_rate": (b.get("raw_all_rows") or {}).get("base_rate_realised"),
                "mean_predicted": (b.get("raw_all_rows") or {}).get("mean_predicted"),
                "reading": v.get("reading"),
            }
    out["V2-H3_the_probability_is_a_ranking_score_not_a_frequency"] = {
        "per_arm": h3,
        "verdict": ("SUPPORTED" if any("RANKING SCORE" in v["reading"] for v in h3.values())
                    else "NOT SUPPORTED" if h3 else "CANNOT DETERMINE"),
    }

    # V2-H4: residual vs raw, as a PAIRED monthly test per family.
    rvr = (rep.get("residual_vs_raw", {}) or {}).get("1m", {}) or {}
    fams_ahead = [f for f, d in rvr.items()
                  if (d.get("t_stat_paired") or -9) >= 1.0
                  and (d.get("mean_monthly_difference") or 0) > 0]
    fams_behind = [f for f, d in rvr.items()
                   if (d.get("t_stat_paired") or 9) <= -1.0]
    out["V2-H4_residual_form_beats_raw_form"] = {
        "paired_residual_minus_raw_1m": rvr,
        "families_where_residual_is_ahead_at_t_ge_1": fams_ahead,
        "families_where_RAW_is_ahead_at_t_ge_1": fams_behind,
        "terminal_wealths_1m": {a: tw(a) for a in
                                ("encoder__raw", "encoder__residual",
                                 "encoder_clf__raw", "encoder_clf__residual",
                                 "lgbm__raw", "lgbm__residual",
                                 "ridge__raw", "ridge__residual")},
        "verdict": ("SUPPORTED" if fams_ahead and not fams_behind else
                    "NOT SUPPORTED -- the RAW form is ahead" if fams_behind and not fams_ahead
                    else "MIXED" if (fams_ahead and fams_behind) else "NOT SUPPORTED"),
        "rule": "paired monthly difference (residual minus raw) per model family, "
                "t >= 1.0 with a positive mean. Two terminal wealths are one draw.",
    }

    # the shadow book's own number, answered.
    b1 = (cal.get("1m", {}) or {}).get("lgbm_clf", {})
    raw = b1.get("raw_all_rows", {}) if isinstance(b1, dict) else {}
    br = raw.get("base_rate_realised")
    mp = raw.get("mean_predicted")
    bias = None if (br is None or mp is None) else round(mp - br, 5)
    shadow_top = 0.494          # the 2026-09-02 book's top score, as published
    out["the_shadow_book_question"] = {
        "asked": "the 2026-09-02 shadow book's top P(beat) was 0.494 -- does that mean "
                 "'the model dislikes today' or 'the scores are uncalibrated'?",
        "unconditional_base_rate_1m": br,
        "mean_predicted_1m_OOS": mp,
        "model_level_bias_vs_base_rate": bias,
        "shadow_top_score": shadow_top,
        "shadow_top_score_minus_base_rate": (None if br is None
                                             else round(shadow_top - br, 5)),
        "shadow_top_score_debiased": (None if bias is None
                                      else round(shadow_top - bias, 5)),
        "answer": (
            "NOT 'dislikes today'. The reference is the realised BASE RATE "
            f"({br}), never 0.5 -- most individual stocks lose to a cap-weighted market "
            "in a given month, so a forecast below 0.5 is the normal case and carries no "
            f"bearish content. The model's own level sits {bias:+} relative to that base "
            f"rate across the whole OOS panel, so 0.494 debiases to about "
            f"{None if bias is None else round(shadow_top - bias, 4)} -- "
            f"{'above' if (br is not None and shadow_top - (bias or 0) > br) else 'at or below'} "
            "the base rate. Whether the number is a literal frequency at all is V2-H3."
            if br is not None and bias is not None
            else "CANNOT DETERMINE -- no 1m calibration block"),
    }
    return out


def _f(v, nd=4):
    return "n/a" if v is None else f"{v:.{nd}f}"


def _print(rep: dict) -> None:
    for hk, sb in rep.get("scoreboards", {}).items():
        print("\n" + "=" * 104)
        print(f"OOS SCOREBOARD -- horizon {hk}, walk-forward, excess over the VW market")
        print("=" * 104)
        print(f"{'arm':<26} {'IC':>8} {'IC t':>7} {'TW net':>8} {'TW mkt':>8} "
              f"{'exc/yr':>8} {'pair t':>7} {'MaxDD':>8} {'turn':>6}")
        rows = []
        for name, row in sb.items():
            bk = row.get("book_top50_vw", {})
            rows.append((bk.get("terminal_wealth_net") or -1, name, row.get("rank_ic", {}), bk))
        for _k, name, ic, bk in sorted(rows, reverse=True):
            print(f"{name:<26} {_f(ic.get('mean_ic')):>8} {_f(ic.get('t_stat'), 2):>7} "
                  f"{_f(bk.get('terminal_wealth_net'), 3):>8} "
                  f"{_f(bk.get('terminal_wealth_market_same_months'), 3):>8} "
                  f"{_f(bk.get('annualised_excess')):>8} "
                  f"{_f(bk.get('t_stat_paired_vs_market'), 2):>7} "
                  f"{_f((bk.get('risk') or {}).get('max_drawdown_net'), 3):>8} "
                  f"{_f(bk.get('mean_turnover'), 2):>6}")
        print(f"  champion: {rep['champions'][hk]['champion']}   "
              f"nulls flat: {rep['null_controls'][hk].get('all_nulls_flat')}")
    for k, v in rep.get("verdicts", {}).items():
        print(f"\n{k}: {v.get('verdict', v.get('answer', ''))}")


# ------------------------------------------------ the overlap correction pass

def append_overlap_correction(horizons=HORIZONS, verbose: bool = True) -> int:
    """Re-grade the SAVED OOS predictions for overlap, and append to the receipt.

    A separate pass, on purpose. A 12-month forward target sampled monthly is
    the same twelve months of market history counted twelve times, so an IC t
    computed across 96 monthly draws divides by sqrt(96) when the independent
    draws number about eight. `docs/TRIAL_RESULT_2026-09-03_BAND_HORIZON.md`
    measured exactly that on the engine prior: the naive t climbs 14.6 -> 44.2
    across horizons while the block t stays flat at ~13.6-14.6. Publishing the
    naive number again, one document later, would be the same error twice.

    TWO SERIES, TWO DIFFERENT ANSWERS, and the distinction is the point:

      * the IC series is computed on OVERLAPPING TARGETS. Its t is inflated by
        roughly sqrt(h) and must be read as `t_block` / `t_newey_west`.
      * the overlapping BOOK's monthly returns are returns an account actually
        earns, one after another, so terminal wealth and drawdown are exactly
        right. What overlap does to them is make them SERIALLY CORRELATED --
        the book only turns over 1/h of itself a month -- so the t of the
        paired excess needs a HAC correction, but the money does not.

    Nothing is recomputed from a model: this reads `oos_predictions_v2.parquet`
    and the receipt that is already on disk, and only ADDS a key.
    """
    if not RECEIPT.exists():
        raise SystemExit(f"REFUSED: {RECEIPT.name} does not exist -- run the main pass first")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    path = PRED_DIR / "oos_predictions_v2.parquet"
    if not path.exists():
        raise SystemExit(f"REFUSED: {path.name} is missing -- the correction would have "
                         "to re-fit, and a correction that re-fits is a different run")
    preds = pd.read_parquet(path)
    df = D.load()
    out: dict = {
        "why": "a 12-month forward target sampled monthly is one history counted 12 times; "
               "the naive IC t divides by sqrt(months) when the independent draws number "
               "about months/h. See docs/TRIAL_RESULT_2026-09-03_BAND_HORIZON.md.",
        "what_is_and_is_not_affected": {
            "rank_ic_t": "INFLATED by overlap -- read t_block or t_newey_west",
            "terminal_wealth": "NOT affected -- the overlapping book's monthly returns are "
                               "earned sequentially and compound honestly",
            "max_drawdown": "NOT affected -- same reason",
            "paired_t_vs_market": "serially correlated, not overlapping; HAC-corrected here",
        },
        "horizons": {},
    }
    for h in horizons:
        y = f"excess_vw_{h}m"
        cols = [c for c in preds.columns if c.endswith(f"__{h}m")]
        if not cols:
            continue
        block: dict = {}
        joined = df[["permno", "month", "entry_date", y, "fwd_1m", "mkt_vw_1m",
                     "market_cap", "log_dollar_vol_20d"]].join(preds[cols])
        joined = joined[joined[y].notna()]
        for c in cols:
            arm = c[: -len(f"__{h}m")]
            sub = joined[joined[c].notna()]
            if sub.empty:
                continue
            ics = E.monthly_ic_series(sub, c, y)
            if ics.empty:
                continue
            row = {"rank_ic_overlap_corrected": E.overlap_corrected(ics, h),
                   "mean_ic": round(float(ics.mean()), 5)}
            bk = (E.book(sub, c, k=BOOK_K, weight="vw", return_series=True) if h == 1
                  else E.overlapping_book(sub, c, h, k=BOOK_K, weight="vw",
                                          with_risk=False, return_series=True))
            s = bk.get("_series")
            if s is not None:
                spread = (s["net"] - s["market"]).dropna()
                row["paired_excess_vs_market_hac"] = E.overlap_corrected(spread, h)
                row["terminal_wealth_net"] = bk.get("terminal_wealth_net")
            block[arm] = row
            if verbose:
                r = row["rank_ic_overlap_corrected"]
                print(f"    {h}m {arm:<28} IC {row['mean_ic']:+.4f}  "
                      f"t_naive {r.get('t_naive')}  t_block {r.get('block_t_block')}  "
                      f"n_eff {r.get('block_n_effective')}")
        out["horizons"][f"{h}m"] = block
    receipt["overlap_correction"] = out
    receipt["overlap_correction_appended_at_utc"] = datetime.now(
        timezone.utc).isoformat(timespec="seconds")
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"  overlap correction appended -> {RECEIPT.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true",
                    help="2 test years, ridge+lgbm only -- plumbing, not a result")
    ap.add_argument("--horizons", type=int, nargs="*", default=list(HORIZONS))
    ap.add_argument("--overlap-correction", action="store_true",
                    help="append the overlap-corrected t block to an existing receipt "
                         "from the saved OOS predictions; fits nothing")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if a.overlap_correction:
        return append_overlap_correction(tuple(a.horizons), verbose=not a.quiet)
    years = (2016, 2017) if a.smoke else TEST_YEARS
    return run(horizons=tuple(a.horizons), test_years=years, smoke=a.smoke,
               verbose=not a.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
