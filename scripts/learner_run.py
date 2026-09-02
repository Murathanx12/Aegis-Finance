"""AEGIS LEARNER v1 -- build the PIT table, train every arm, grade them, seal.

    python -m scripts.learner_run                 # build if missing, then everything
    python -m scripts.learner_run --build         # rebuild the training table only
    python -m scripts.learner_run --reuse-table   # skip the build, train + grade

WHAT THIS PRODUCES
==================
`backend/data/optimus/tracker_backtest/learner_v1.json` -- the receipt, with a
PRE-REGISTRATION HEADER WRITTEN BEFORE ANY MODEL IS FITTED. The header is
flushed to disk first and the tables are appended afterwards, so the hypothesis,
the decision rule and the honest prior are on disk even if the run dies, and
cannot be edited into agreement with whatever came out.

LICENCE: PRODUCT_EXPERIMENT.
The learner may explore dirty. It may be post-hoc, it may try twenty variants,
and it needs no significance gate to be built. What does not relax, and is
enforced in code rather than intention:

    1. no information acted on before it was public   -> merge_asof on
       statpers + lag, targets NULL until matured, splits by DATE only;
    2. no target leakage                              -> train rows must have
       MATURED before the test year begins, not merely be dated before it;
    3. costs are never omitted                        -> 10 bps/side on
       measured turnover, gross printed beside net;
    4. a candidate that enters forward paper is FROZEN -> the shadow seals a
       model vintage hash and places nothing.

The learner has ZERO broker authority. `learner/shadow.py` writes a JSON file.
No order path imports anything in `learner/`.
"""

from __future__ import annotations

import argparse
import hashlib
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
from learner import dataset as D                            # noqa: E402
from learner import evaluate as E                           # noqa: E402
from learner import models as M                             # noqa: E402
from learner import prior as P                              # noqa: E402

RECEIPT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "learner_v1.json"
MODEL_DIR = REPO / "backend" / "data" / "optimus" / "learner" / "models"

TEST_YEARS = tuple(range(2016, 2025))
PRIMARY_HORIZON = 1
SECONDARY_HORIZONS = (3, 6, 12)
BOOK_K = 50
NULL_ARM = "NULL_shuffled_target__lgbm_raw"


# --------------------------------------------------------- the prereg header

def prereg_header() -> dict:
    """Written to disk BEFORE the first fit. Not editable afterwards without
    it being obvious that it was."""
    return {
        "artefact": "AEGIS_LEARNER_v1",
        "licence": "PRODUCT_EXPERIMENT",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "written_before": "any model was fitted; the tables below were appended after",
        "hypothesis": (
            "H1: an ML model that learns the ENGINE'S RESIDUALS (target = realised excess "
            "minus BAND_PRIOR v2's banded expectation) beats the engine prior alone, out of "
            "sample, on BOTH rank IC and the terminal wealth of a monthly top-50 "
            "value-weighted book, 2016-2024."),
        "sub_hypotheses": {
            "H2": "the residual arm beats the raw arm -- i.e. handing the model the prior as "
                  "an OFFSET is better than handing it the prior as a FEATURE.",
            "H3": "the learner adds rank IC INSIDE the admissible region (ratio 1.5-5), "
                  "where the engine says one constant and S33 found six simple features empty.",
            "H4": "a neural arm beats a linear one -- i.e. the residual structure is "
                  "non-linear rather than a tilt.",
        },
        "honest_prior_before_running": (
            "Probably small or zero INSIDE the bands: S33's Fama-MacBeth found all six of "
            "upside / consensus / ret_12m / drawdown_60d / log_coverage / log_dollar_vol with "
            "|t| < 1.5 over 143 months inside that region, and this learner's features are a "
            "richer version of the same family, not a new information source. Possibly real "
            "ACROSS bands -- but the band prior already captures the across-band structure by "
            "construction, so an 'ML wins' there is mostly the learner rediscovering the "
            "prior. The outcome I would bet on is H1 NEGATIVE, H2 mildly positive, H3 "
            "NEGATIVE, H4 no difference."),
        "primary_metric": (
            "terminal wealth, net of 10bps/side on measured turnover, of a monthly top-50 "
            "value-weighted book selected on predicted excess return, pooled over the "
            "walk-forward OOS years 2016-2024."),
        "secondary_metrics": [
            "rank IC (cross-sectional Spearman per month, t across MONTHS -- the date-block n)",
            "calibration slope of realised on predicted across within-month deciles",
            "top-decile minus bottom-decile realised excess, monthly, with t",
            "the same, restricted to the admissible region (H3)",
        ],
        "decision_rule_declared_in_advance": {
            "champion": (
                "the arm with the highest OOS net terminal wealth of the top-50 VW book, "
                "SUBJECT TO (i) rank IC t >= 2.0 and (ii) paired-vs-market t >= 1.0 with a "
                "positive annualised excess."),
            "if_nothing_qualifies": (
                "champion = `prior` (the incumbent engine) and `ml_earned_the_seat` = false. "
                "The shadow still runs, on the incumbent, and still places nothing."),
            "h1_verdict": "SUPPORTED only if a learnable arm is champion AND its net terminal "
                          "wealth exceeds the `prior` baseline's on the same months.",
            "h3_verdict": "SUPPORTED only if the champion's rank IC t inside the admissible "
                          "region is >= 2.0.",
        },
        "benchmark": {
            "primary": "value-weighted CRSP common-stock market (excess = stock - VW market)",
            "also_stored": "equal-weighted",
            "why": "an EW benchmark is a SIZE ARTEFACT -- a small-cap portfolio wearing a "
                   "market's name. VW is primary; EW is reported so the band prior (which was "
                   "measured against EW) is not silently advantaged or disadvantaged.",
        },
        "known_flattery_of_the_incumbent": (
            "BAND_PRIOR v2's four constants were fitted on the FULL 2013-2024 window, so the "
            "`prior` baseline knows the test years and the ML arms do not. Beating it OOS is "
            "therefore a HARD test. Stated here rather than discovered in the discussion."),
        "walk_forward": {
            "test_years": list(TEST_YEARS),
            "train_rule": "every row whose TARGET HAD MATURED before 1 Jan of the test year. "
                          "Not 'dated before' -- a Nov-2015 row with a 12m target resolves in "
                          "Nov 2016 and would hand a 2016 test year eleven months of itself.",
            "splits": "expanding window, by DATE only. Never random k-fold.",
        },
        "null_control": (
            "`" + NULL_ARM + "` runs the SAME pipeline, rows and costs with the training "
            "target permuted WITHIN each month. It destroys the feature-outcome pairing and "
            "leaves the month structure, the market factor and every other moving part alone. "
            "Any OOS rank IC it earns is plumbing, not signal. Expected: IC ~ 0, |t| < 2. If "
            "the null scores, EVERY number in this receipt is void and says so."),
        "shadow": "learner/shadow.py scores the live tracker day file with a champion trained "
                  "on shadow-mappable features only, writes a top-10 @ 8.3% book to "
                  "backend/data/optimus/learner/, and PLACES NOTHING.",
    }


# ------------------------------------------------------------ the arm runner

def arm_names() -> list[str]:
    out = list(B.BASELINE_NAMES)
    for kind in M.LEARNABLE:
        for arm in M.ARMS:
            out.append(f"{kind}__{arm}")
    out.append(M.CLASSIFIER)
    return out


def walk_forward(df: pd.DataFrame, horizon: int, feature_cols: list[str],
                 kinds: tuple[str, ...], with_classifier: bool,
                 verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """Out-of-sample predictions for every arm, one column each.

    Every prediction on a test row was made by a model that saw only rows whose
    targets had already matured before that test year opened.
    """
    preds = pd.DataFrame(index=df.index, dtype="float64")
    fits: dict = {}
    for year, tr, te in D.walk_forward_splits(df, TEST_YEARS, horizon):
        t0 = time.time()
        train, test = df.loc[tr], df.loc[te]
        for name in B.BASELINE_NAMES:
            if name not in preds.columns:
                preds[name] = np.nan
            preds.loc[te, name] = B.predict(name, train, test, horizon)
        for kind in kinds:
            for arm in M.ARMS:
                col = f"{kind}__{arm}"
                if col not in preds.columns:
                    preds[col] = np.nan
                p, meta = M.fit_predict(kind, arm, train, test, feature_cols, horizon)
                preds.loc[te, col] = p
                fits.setdefault(col, {})[str(year)] = {
                    k: v for k, v in meta.items() if k != "feature_cols"}
        if with_classifier:
            if M.CLASSIFIER not in preds.columns:
                preds[M.CLASSIFIER] = np.nan
            p, meta = M.fit_predict_proba(train, test, feature_cols, horizon)
            preds.loc[te, M.CLASSIFIER] = p
            fits.setdefault(M.CLASSIFIER, {})[str(year)] = meta

            # THE NULL. Same pipeline, same rows, same costs -- with the
            # training target permuted WITHIN each month. If this scores, the
            # result is plumbing and not signal. A null owes two tests; this is
            # the leak test, and the era split below is the regime test.
            if NULL_ARM not in preds.columns:
                preds[NULL_ARM] = np.nan
            p, meta = M.fit_predict("lgbm", "raw", train, test, feature_cols,
                                    horizon, shuffle_target=True)
            preds.loc[te, NULL_ARM] = p
            fits.setdefault(NULL_ARM, {})[str(year)] = {
                k: v for k, v in meta.items() if k != "feature_cols"}
        if verbose:
            print(f"    {year}: train {len(tr):,} rows / "
                  f"{train['month'].nunique()} months -> test {len(te):,} rows "
                  f"({time.time() - t0:.1f}s)")
    return preds, fits


def grade_all(df: pd.DataFrame, preds: pd.DataFrame, horizon: int,
              full: bool = True) -> dict:
    """Grade every arm on the pooled OOS rows."""
    scored = df.join(preds, rsuffix="_pred")
    y = f"excess_vw_{horizon}m"
    scored = scored[scored[y].notna()]
    out: dict = {}
    for col in preds.columns:
        sub = scored[scored[col].notna()]
        if sub.empty:
            continue
        calibrated = (B.is_calibrated(col) if col in B.BASELINE_NAMES
                      else col != M.CLASSIFIER)
        row = E.grade(sub, col, horizon, is_calibrated=calibrated,
                      with_books=full, k=BOOK_K)
        if full:
            row["by_era"] = E.grade_by_era(sub, col, horizon)
            row["by_band"] = E.grade_by_band(sub, col, horizon)
        out[col] = row
    return out


def choose_champion(scoreboard: dict) -> dict:
    """The pre-declared rule, applied mechanically. No judgement at this step."""
    qualifying = []
    for name, row in scoreboard.items():
        if name == NULL_ARM:
            continue          # the null is a check, never a candidate
        bk = row.get("book_top50_vw") or {}
        ic = row.get("rank_ic") or {}
        ic_t = ic.get("t_stat")
        pair_t = bk.get("t_stat_paired_vs_market")
        exc = bk.get("annualised_excess")
        tw = bk.get("terminal_wealth_net")
        ok = (ic_t is not None and ic_t >= 2.0 and pair_t is not None and pair_t >= 1.0
              and exc is not None and exc > 0 and tw is not None)
        if ok:
            qualifying.append((tw, name))
    if not qualifying:
        return {"champion": "prior", "ml_earned_the_seat": False,
                "reason": "no arm cleared the pre-declared bar (rank IC t >= 2.0 AND "
                          "paired-vs-market t >= 1.0 AND positive annualised excess). "
                          "The incumbent keeps the seat."}
    qualifying.sort(reverse=True)
    tw, name = qualifying[0]
    return {"champion": name,
            "ml_earned_the_seat": name not in B.BASELINE_NAMES,
            "terminal_wealth_net": tw,
            "qualifying_arms": [n for _, n in qualifying],
            "reason": "highest OOS net terminal wealth among arms clearing the bar"}


# --------------------------------------------------------------- final fits

def fit_final(df: pd.DataFrame, kind: str, arm: str, feature_cols: list[str],
              horizon: int, tag: str) -> dict:
    """Refit the chosen kind/arm on EVERY matured row, and seal it for the
    shadow. This model is never graded -- it is the one that scores today."""
    import joblib
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    train = df[df[f"excess_vw_{horizon}m"].notna()]
    if kind == M.CLASSIFIER:
        model, cols, meta = M.fit_classifier(train, feature_cols, horizon)
    else:
        _pred, meta, model = M.fit_predict(kind, arm, train, train.head(1000),
                                           feature_cols, horizon, return_model=True)
        cols = M.arm_features(feature_cols, arm, horizon)
    path = MODEL_DIR / f"champion_{tag}.joblib"
    payload = {
        "kind": kind, "arm": arm, "horizon_months": horizon,
        "feature_cols": cols, "model": model,
        "schema_hash": D.schema_hash(shadow_only=(tag == "shadow")),
        "prior_version": P.PRIOR_VERSION,
        "trained_rows": int(len(train)),
        "trained_through_month": str(train["month"].max()),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prediction_unit": M.prediction_unit(kind),
    }
    joblib.dump(payload, path)
    vintage = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    payload_meta = {k: v for k, v in payload.items() if k != "model"}
    payload_meta["model_vintage_sha256_16"] = vintage
    payload_meta["path"] = str(path)
    payload_meta["fit_meta"] = {k: v for k, v in meta.items() if k != "feature_cols"}
    if kind == "lgbm":
        payload_meta["gain_importance_top"] = M.gain_importance(model, cols)
    # The vintage hash has to live INSIDE the artefact too, or a shadow book
    # could name a hash that the file it loaded does not carry.
    payload["model_vintage_sha256_16"] = vintage
    joblib.dump(payload, path)
    return payload_meta


# ------------------------------------------------------------------- the run

def run(rebuild: bool, verbose: bool = True) -> int:
    t_start = time.time()
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)

    # 1. HEADER FIRST, ON DISK, BEFORE ANYTHING IS FITTED.
    receipt: dict = {"prereg_header": prereg_header()}
    RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"  prereg header sealed -> {RECEIPT}")

    # 2. the table
    if rebuild or not D.TRAIN_TABLE.exists():
        print("  building the PIT training table ...")
        df, build_receipt = D.build(2013, 2024, verbose=verbose)
        D.save(df, build_receipt)
    else:
        df = D.load()
        build_receipt = json.loads(D.SCHEMA_RECEIPT.read_text(encoding="utf-8"))["build"]
        print(f"  reusing {D.TRAIN_TABLE.name}: {len(df):,} rows")
    receipt["dataset"] = build_receipt
    receipt["dataset"]["schema"] = D.feature_schema()
    receipt["dataset"]["company_state_registered"] = D.company_state_schema()
    receipt["prior"] = P.describe()
    receipt["models"] = M.describe()
    receipt["baselines"] = B.describe()
    receipt["evaluation_conventions"] = {
        "cost_bps_per_side": E.COST_BPS_PER_SIDE,
        "cost_basis": "measured weight turnover, both sides; gross reported beside net",
        "t_stat_n": "MONTHS (date blocks), never name-months",
        "book": f"monthly top-{BOOK_K}, value-weighted, ties broken by permno ascending",
        "tradable_variant_floor_usd": E.TRADABLE_DOLLAR_VOL,
    }

    feature_cols = D.feature_columns()
    shadow_cols = D.feature_columns(shadow_only=True)
    print(f"  features: {len(feature_cols)} full / {len(shadow_cols)} shadow-mappable")

    # 3. the primary horizon: every arm
    print(f"  walk-forward, horizon {PRIMARY_HORIZON}m, all arms ...")
    preds, fits = walk_forward(df, PRIMARY_HORIZON, feature_cols, M.LEARNABLE,
                               with_classifier=True, verbose=verbose)
    scoreboard = grade_all(df, preds, PRIMARY_HORIZON, full=True)
    receipt["scoreboard_1m"] = scoreboard
    receipt["fit_metadata_1m"] = fits
    # The OOS predictions themselves, kept so a later session can re-grade
    # without re-fitting -- and so "what did it buy?" is answerable from a file
    # rather than from a rerun that might not reproduce.
    pred_path = D.OUT_DIR / "oos_predictions_1m.parquet"
    df.loc[:, ["permno", "month", "entry_date"]].join(preds).to_parquet(
        pred_path, index=False)
    receipt["oos_predictions_path"] = str(pred_path)
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")

    # 4. the secondary horizons: the cheap arms only, rank IC and spread
    receipt["scoreboard_other_horizons"] = {}
    for h in SECONDARY_HORIZONS:
        print(f"  walk-forward, horizon {h}m, ridge + lgbm ...")
        ph, fh = walk_forward(df, h, feature_cols, ("ridge", "lgbm"),
                              with_classifier=False, verbose=verbose)
        receipt["scoreboard_other_horizons"][f"{h}m"] = grade_all(df, ph, h, full=False)
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")

    # 5. the champion, by the rule declared in the header
    champ = choose_champion(scoreboard)
    receipt["champion_selection"] = champ
    print(f"  CHAMPION: {champ['champion']}  (ml_earned_the_seat="
          f"{champ['ml_earned_the_seat']})")

    # 6. the verdicts, mechanically
    prior_tw = (scoreboard.get("prior", {}).get("book_top50_vw", {})
                .get("terminal_wealth_net"))
    champ_row = scoreboard.get(champ["champion"], {})
    champ_tw = champ_row.get("book_top50_vw", {}).get("terminal_wealth_net")
    adm = (champ_row.get("by_band", {})
           .get("ADMISSIBLE_REGION_ratio_1_5_to_5", {}).get("rank_ic", {}))
    adm_t = adm.get("t_stat")
    best_res = max(
        (scoreboard.get(f"{k}__residual", {}).get("book_top50_vw", {})
         .get("terminal_wealth_net") or -np.inf) for k in M.LEARNABLE)
    best_raw = max(
        (scoreboard.get(f"{k}__raw", {}).get("book_top50_vw", {})
         .get("terminal_wealth_net") or -np.inf) for k in M.LEARNABLE)
    receipt["verdicts"] = {
        "H1_engine_plus_residual_beats_engine_alone": {
            "verdict": ("SUPPORTED" if (champ["ml_earned_the_seat"] and champ_tw is not None
                                        and prior_tw is not None and champ_tw > prior_tw)
                        else "NOT SUPPORTED"),
            "champion_terminal_wealth_net": champ_tw,
            "prior_terminal_wealth_net": prior_tw,
        },
        "H2_residual_arm_beats_raw_arm": {
            "best_residual_terminal_wealth": (None if best_res == -np.inf else best_res),
            "best_raw_terminal_wealth": (None if best_raw == -np.inf else best_raw),
            "verdict": ("residual" if best_res > best_raw else "raw") + " arm ahead on "
                       "terminal wealth (this is a RANKING, not a significance test: two "
                       "terminal wealths are one draw of a correlated pair)",
        },
        "H3_learner_adds_inside_the_admissible_band": {
            "champion_rank_ic_inside_region": adm,
            "verdict": "SUPPORTED" if (adm_t is not None and adm_t >= 2.0) else "NOT SUPPORTED",
            "note": "the region where the engine says ONE constant and S33 found six simple "
                    "features empty (all |t| < 1.5 over 143 months)",
        },
    }

    # 7. seal the champion(s) for the shadow
    print("  fitting final champion(s) on every matured row ...")
    sealed: dict = {}
    if champ["ml_earned_the_seat"]:
        # `lgbm_clf` has no arm suffix: it is one head, not two arms.
        kind, arm = ((M.CLASSIFIER, "engine_feature")
                     if champ["champion"] == M.CLASSIFIER
                     else champ["champion"].split("__"))
    else:
        # The incumbent won. The shadow still needs SOMETHING to rank with, and
        # ranking on four constants is not a ranking, so the shadow's model is
        # the best learnable arm by terminal wealth -- explicitly labelled as
        # NOT having cleared the bar, so no reader mistakes it for a champion.
        learn = [(scoreboard.get(f"{k}__{a}", {}).get("book_top50_vw", {})
                  .get("terminal_wealth_net") or -np.inf, k, a)
                 for k in M.LEARNABLE for a in M.ARMS]
        learn.sort(reverse=True)
        _tw, kind, arm = learn[0]
        sealed["note"] = ("no arm cleared the bar; the shadow model is the best learnable arm "
                          "by terminal wealth and is NOT a champion")
    sealed["kind"], sealed["arm"] = kind, arm
    sealed["full"] = fit_final(df, kind, arm, feature_cols, PRIMARY_HORIZON, "full")
    # The shadow's own model: trained on the columns a tracker day file can
    # actually supply. Median-imputing a third of a model's inputs at score
    # time and calling the result a prediction is not honest, so the shadow
    # gets a model that never had those inputs.
    print("  walk-forward for the SHADOW feature set (honest OOS score) ...")
    if kind == M.CLASSIFIER:
        sp = pd.DataFrame(index=df.index, dtype="float64")
        sp[M.CLASSIFIER] = np.nan
        for _y, tr, te in D.walk_forward_splits(df, TEST_YEARS, PRIMARY_HORIZON):
            p, _m = M.fit_predict_proba(df.loc[tr], df.loc[te], shadow_cols, PRIMARY_HORIZON)
            sp.loc[te, M.CLASSIFIER] = p
        col = M.CLASSIFIER
    else:
        sp, _sf = walk_forward(df, PRIMARY_HORIZON, shadow_cols, (kind,),
                               with_classifier=False, verbose=verbose)
        col = f"{kind}__{arm}"
    sb = grade_all(df, sp[[col]], PRIMARY_HORIZON, full=True)
    sealed["shadow_feature_set_oos"] = sb.get(col, {})
    sealed["shadow_feature_set_oos_is_post_hoc"] = (
        "This score was computed AFTER the champion kind was chosen on the full feature "
        "set. It is an honest walk-forward number, but it is one more comparison in the "
        "same multiplicity family and was not the pre-declared decision metric.")
    sealed["shadow"] = fit_final(df, kind, arm, shadow_cols, PRIMARY_HORIZON, "shadow")
    receipt["sealed_models"] = sealed

    receipt["runtime_seconds"] = round(time.time() - t_start, 1)
    RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    _print_scoreboard(receipt)
    print(f"\n  receipt -> {RECEIPT}  ({receipt['runtime_seconds']}s)")
    return 0


def _print_scoreboard(rep: dict) -> None:
    sb = rep.get("scoreboard_1m", {})
    print("\n" + "=" * 96)
    print("OOS SCOREBOARD -- horizon 1m, walk-forward 2016-2024, excess over the VW market")
    print("=" * 96)
    print(f"{'arm':<22} {'IC':>8} {'IC t':>7} {'D10-D1/yr':>10} "
          f"{'TW net':>8} {'TW mkt':>8} {'exc/yr':>8} {'pair t':>7}")
    rows = []
    for name, row in sb.items():
        ic = row.get("rank_ic", {})
        bk = row.get("book_top50_vw", {})
        tb = row.get("top_minus_bottom_decile", {})
        rows.append((bk.get("terminal_wealth_net") or -1, name, ic, bk, tb))
    for _k, name, ic, bk, tb in sorted(rows, reverse=True):
        print(f"{name:<22} {_f(ic.get('mean_ic'), 4):>8} {_f(ic.get('t_stat'), 2):>7} "
              f"{_f(tb.get('annualised_spread'), 4):>10} "
              f"{_f(bk.get('terminal_wealth_net'), 3):>8} "
              f"{_f(bk.get('terminal_wealth_market_same_months'), 3):>8} "
              f"{_f(bk.get('annualised_excess'), 4):>8} "
              f"{_f(bk.get('t_stat_paired_vs_market'), 2):>7}")
    print("\nINSIDE THE ADMISSIBLE REGION (ratio 1.5-5) -- rank IC only")
    for name, row in sb.items():
        a = (row.get("by_band", {}) or {}).get("ADMISSIBLE_REGION_ratio_1_5_to_5", {})
        ic = a.get("rank_ic", {})
        if ic:
            print(f"  {name:<22} IC {_f(ic.get('mean_ic'), 4):>8}  "
                  f"t {_f(ic.get('t_stat'), 2):>6}  months {ic.get('months')}")
    for k, v in rep.get("verdicts", {}).items():
        print(f"\n{k}: {v.get('verdict')}")


def _f(v, nd):
    return "n/a" if v is None else f"{v:.{nd}f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="rebuild the training table")
    ap.add_argument("--reuse-table", action="store_true",
                    help="never rebuild, even if the table is stale")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    return run(rebuild=(a.build and not a.reuse_table), verbose=not a.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
