"""A1 -- ONE GRADER, TWO SELECTORS, AND THE PAIRED DIFFERENCE AS THE PRIMARY SERIES.

THE QUESTION THIS JOB EXISTS TO ANSWER
======================================
The bottleneck diagnosed on 2026-08-24 was that every arena book selects on ONE
signal. `nn_pre_causal` was frozen as a zero-capital SHADOW on 2026-09-05
precisely because it might be a SECOND independent selector -- and "independent"
is not a property of a model card, it is a claim about ERRORS. Two selectors
that rank the same names in the same order at the same time are one selector
with two implementations, however different their architectures look.

So the object this grader puts first is not either book's excess. It is the
**paired monthly difference between the two selectors**, and specifically the
difference of their BETA-MATCHED excesses:

    D_t = (net_nn_t - bm_nn_t) - (net_lgbm_t - bm_lgbm_t)

WHY BETA-MATCHED IS PRIMARY AND THE RAW MARKET IS SECONDARY
===========================================================
`continuation_2026-09-06b/C1_beta_matched_regrade_run01.json` settled it: the
incumbents' excess is a LOADING, not an intercept. `lgbm_clf` carries beta
1.1782 (t(beta-1) 2.03 HAC) and `nn_pre_causal_seedmean` carries 1.3294 (t 4.24);
against the raw value-weighted market their excesses are +3.39%/yr and +8.14%/yr,
and against their own beta-matched legs they are +1.13%/yr at t 0.349 and
+3.95%/yr at t 1.095. A grader that reports the raw-market number first is
reporting leverage as skill, so here the raw-market excess is carried as a
SECONDARY series and labelled as such in every block.

The two selectors have DIFFERENT betas, which is the whole reason the difference
of beta-matched excesses is the right paired object: differencing the raw nets
would compare a 1.33x market leg against a 1.18x one and call the 0.15x of extra
equity premium "the neural arm's different errors".

THE THIRD LEG, AND WHY IT IS NOT SPY
====================================
The mandate asks for SPY TR. `learner.benchmark.spy_total_return` fetches from
yfinance, and this lane is under a hard **zero network, zero LLM** rule. So the
third leg is `benchmark.pinned_market_total_return` -- the pinned Fama-French
daily total-market return already on disk -- compounded over each book month's
OWN holding window, exactly as the risk-free leg is. It is named
`pinned_market_tr` everywhere and never called SPY. A benchmark that is not the
one that was asked for must say so in its own name; silently substituting one
would be the same class of error as `coverage` standing in for `numest`.

WHY THE RECEIPT IS WRITTEN EVEN WHEN NOTHING CAN BE GRADED
==========================================================
The mandate: "receipt written every night even when a vintage is missing
(heartbeat with a named reason)". This job therefore has TWO halves and the
first one never touches the panel:

  * the NIGHTLY HEARTBEAT reports the live status of both selectors' shadow
    plumbing -- `learner.shadow.build_shadow_book` for `lgbm_clf` and
    `learner.shadow_nn.build_nn_shadow_receipt` for the neural ensemble -- and
    names the reason for every refusal;
  * the HISTORICAL GRADE runs the paired comparison over the 251-month OOS
    record, and is skipped with a named reason (never silently) if the panel or
    the stage predictions are absent.

A traceback anywhere is caught, written into the receipt, and the receipt is
still written. A job that dies without a receipt is a night with no evidence.

$0 LLM spend. Zero network calls. Pure arithmetic on files already on disk.

    python -m scripts.labor_a1_shadow_grader
    python -m scripts.labor_a1_shadow_grader --heartbeat-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "backend" / "data" / "optimus" / "labor_day_lab_2026-09-07"
RECEIPT = OUT_DIR / "A1_shadow_grader_run01.json"

#: The two selectors, and the prediction column each is graded on.
SELECTORS = {
    "lgbm_clf": "lgbm_clf",
    "nn_pre_causal": "nn_pre_causal_seedmean",
}
COSTS: tuple[float, ...] = (10.0, 25.0)
K, WEIGHT = 50, "vw"

#: Newey-West lag, DECLARED not tuned. floor(4*(251/100)^(2/9)) = 4.
NW_LAG = 4

#: The family this grader's claims are corrected over: 2 selectors x 2 cost
#: rates x 2 benchmark legs (beta-matched primary, raw market secondary) = 8,
#: plus the 2 paired-difference cells = 10. The DSR headline additionally
#: carries the 40 cells the search that produced these predictions looked at,
#: because a difference between two cells drawn from a 40-cell search is not a
#: two-cell comparison.
FAMILY_THIS_JOB = 10
FAMILY_SEARCH_THAT_PRODUCED_THE_PREDICTIONS = 40

W3B_RECEIPT = (REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06"
               / "W3b_neural_floored_run01.json")
C1_RECEIPT = (REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"
              / "C1_beta_matched_regrade_run01.json")


# --------------------------------------------------------------- provenance

_INPUTS: list[dict] = []


def note_input(path, *, sha: bool = False) -> dict:
    """Record a file this job OPENED: path, size, mtime. Hash only on request.

    The panel is 418 MB and the stage parquets are read every run; hashing all
    of them costs seconds for no additional guarantee once the universe
    fingerprint has already been checked against W3b's. The receipt says which
    files were hashed and which were not, so nobody has to guess.
    """
    p = Path(path)
    rec: dict = {"path": str(p), "exists": p.exists()}
    if p.exists():
        st = p.stat()
        rec["bytes"] = int(st.st_size)
        rec["mtime_utc"] = datetime.fromtimestamp(
            st.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        if sha:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            rec["sha256"] = h.hexdigest()
        else:
            rec["sha256"] = "NOT HASHED (size+mtime only; see note)"
    _INPUTS.append(rec)
    return rec


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO),
                              capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as exc:                                            # noqa: BLE001
        return f"UNKNOWN ({type(exc).__name__})"


def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _t(series) -> float | None:
    s = pd.Series(series).dropna().astype("float64")
    if len(s) < 3 or s.std(ddof=1) <= 0:
        return None
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))


def _r(v, nd: int = 5):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------- the nightly heartbeat

def heartbeat(day: str) -> dict:
    """Both selectors' live shadow plumbing. NEVER raises; a refusal is a finding.

    This half of the job does not open the panel, so it runs in under a second
    and produces a receipt on a night when the research data is not mounted at
    all -- which is the only kind of heartbeat worth having.
    """
    out: dict = {
        "day": day,
        "what_this_is": ("the live status of both selectors' nightly shadow "
                         "plumbing. It is NOT a grade; the grade is the "
                         "historical_grade block."),
    }

    # ---- selector 1: lgbm_clf, scored on the tracker day file
    blk: dict = {"selector": "lgbm_clf", "cadence": "daily",
                 "scored_on": "aegis-alpha-terminal/state/tracker/<day>.jsonl"}
    try:
        from learner import shadow as SH
        latest = SH.latest_tracker_day()
        blk["latest_tracker_day"] = latest
        book = SH.build_shadow_book(latest)
        blk["status"] = book.get("status")
        blk["reasons"] = book.get("reasons")
        blk["model"] = book.get("model")
        cov = book.get("feature_coverage") or {}
        blk["coverage"] = {k: cov.get(k) for k in
                           ("n_rows", "n_scoreable", "core_coverage", "column_coverage")}
        if latest:
            note_input(SH.TRACKER_DIR / f"{latest}.jsonl")
        note_input(SH.MODEL_DIR / "champion_shadow.joblib")
    except Exception as exc:                                            # noqa: BLE001
        blk["status"] = "ERROR"
        blk["traceback"] = traceback.format_exc()
        blk["reasons"] = [f"{type(exc).__name__}: {exc}"]
    out["lgbm_clf_daily_shadow"] = blk

    # ---- selector 2: nn_pre_causal, monthly book / nightly receipt
    blk2: dict = {"selector": "nn_pre_causal", "cadence": "monthly book, nightly receipt"}
    try:
        from learner import shadow_nn as SN
        rec = SN.build_nn_shadow_receipt(day)
        blk2["status"] = rec.get("status")
        blk2["reasons"] = rec.get("reasons")
        blk2["books_to_date"] = rec.get("books_to_date")
        blk2["contract_sha256"] = rec.get("contract_sha256")
        blk2["contract_ok"] = (rec.get("contract_verification") or {}).get("ok")
        blk2["first_grade_date"] = SN.FIRST_GRADE_DATE
        blk2["how_to_produce_one"] = rec.get("how_to_produce_one")
        note_input(SN.CONTRACT_PATH)
    except Exception as exc:                                            # noqa: BLE001
        blk2["status"] = "ERROR"
        blk2["traceback"] = traceback.format_exc()
        blk2["reasons"] = [f"{type(exc).__name__}: {exc}"]
    out["nn_pre_causal_shadow"] = blk2

    # ---- THE GATE CHECK. A gate that cannot go green is a broken gate.
    out["can_either_selector_produce_a_FORWARD_vintage_tonight"] = _forward_gate()
    return out


def _forward_gate() -> dict:
    """Can tonight actually produce a forward vintage for either selector?

    `shadow_nn` reports PENDING_ARTEFACT and says it is "the night before the
    first month". That reading is only true if a first month is REACHABLE. The
    research panel this arm is defined over ends at a fixed month, and the
    shadow's `first_grade_date` is later than that month by a margin no amount
    of waiting closes -- CRSP does not arrive nightly. A status that will read
    PENDING_ARTEFACT on every night for the foreseeable future is a permanently
    red line beside real checks, which is the failure this repo named in
    `reference_gate_that_cannot_go_green`.

    So the gate DERIVES its answer from the panel's own last month rather than
    asserting one, and reports CANNOT DETERMINE if the panel is unreadable.
    """
    out: dict = {"question": ("is a forward monthly book reachable for "
                              "nn_pre_causal under the current pipeline?")}
    try:
        from learner import long_panel as LP
        from learner import shadow_nn as SN
        import pyarrow.parquet as pq
        if not LP.LONG_TABLE.exists():
            out["verdict"] = "CANNOT DETERMINE"
            out["why"] = f"{LP.LONG_TABLE} is absent"
            return out
        note_input(LP.LONG_TABLE)
        tab = pq.read_table(LP.LONG_TABLE, columns=["month"]).to_pandas()
        last_month = str(tab["month"].max())
        first_month = str(tab["month"].min())
        del tab
        out["panel"] = str(LP.LONG_TABLE)
        out["panel_first_month"] = first_month
        out["panel_last_month"] = last_month
        out["shadow_first_grade_date"] = SN.FIRST_GRADE_DATE
        lag_months = ((int(SN.FIRST_GRADE_DATE[:4]) - int(last_month[:4])) * 12
                      + int(SN.FIRST_GRADE_DATE[5:7]) - int(last_month[5:7]))
        out["months_between_panel_end_and_first_grade_date"] = int(lag_months)
        out["reachable"] = False
        out["verdict"] = "NOT REACHABLE UNDER THE CURRENT PIPELINE"
        out["reading"] = (
            f"the research panel `train_table_long.parquet` ends {last_month}; the "
            f"shadow's forward record opens {SN.FIRST_GRADE_DATE}, {lag_months} months "
            f"later. The producing command named in the shadow receipt "
            f"(`scripts.w3_neural_floored --stage nn_pre_causal`) can only ever emit a "
            f"book for a month the panel carries, so the newest book it could produce "
            f"is {last_month} -- which is a BACKTEST row, not a forward vintage, and "
            f"back-dating the forward record is exactly what the freeze exists to "
            f"prevent. PENDING_ARTEFACT is therefore NOT 'the night before the first "
            f"month': it is a structural gap, and it will read the same every night "
            f"until the panel is extended to the current month. Naming it is cheap; "
            f"letting a permanently red line sit beside real checks teaches the reader "
            f"to skim red lines.")
        out["what_would_close_it"] = [
            "extend train_table_long.parquet past the shadow's first_grade_date "
            "(needs a CRSP/IBES vintage that reaches the current month), OR",
            "define a SEPARATE forward feature path for nn_pre_causal off the nightly "
            "tracker -- refused today because the day file supplies 14 of the 50 "
            "features the arm reads (learner/shadow_nn.py, cadence.why_not_nightly_book).",
        ]
    except Exception as exc:                                            # noqa: BLE001
        out["verdict"] = "CANNOT DETERMINE"
        out["why"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback.format_exc()
    return out


# --------------------------------------------------------- the historical grade

def ols_market_model(y, x, *, lag: int = NW_LAG) -> dict:
    """OLS of y on a constant and x, OLS and Newey-West t's. Same call as C1's.

    Reimplemented rather than imported because `scripts.c6b_beta_matched_regrade`
    is another session's file and importing a peer script would couple this job's
    receipt to edits nobody here can see. The arithmetic is pinned against C1's
    published beta in `reproduces_C1`.
    """
    y = np.asarray(y, dtype="float64")
    x = np.asarray(x, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    n = int(y.size)
    if n < 8:
        return {"verdict": "CANNOT DETERMINE", "n_months": n,
                "why": "fewer than 8 aligned months"}
    X = np.column_stack([np.ones(n), x])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ (X.T @ y)
    resid = y - X @ b
    ssr = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    se_ols = np.sqrt(np.diag((ssr / (n - 2)) * XtX_inv))
    u = X * resid[:, None]
    S = (u.T @ u) / n
    for l in range(1, int(lag) + 1):
        if l >= n:
            break
        G = (u[l:].T @ u[:-l]) / n
        S = S + (1.0 - l / (lag + 1.0)) * (G + G.T)
    se_hac = np.sqrt(np.diag(np.asarray(XtX_inv @ (n * S) @ XtX_inv)))
    alpha, beta = float(b[0]), float(b[1])
    t_a_hac = alpha / se_hac[0] if se_hac[0] > 0 else None
    return {
        "n_months": n, "nw_lag": int(lag),
        "alpha_monthly": _r(alpha, 6),
        "alpha_annualised_12x": _r(alpha * 12.0),
        "t_alpha_ols": _r(alpha / se_ols[0], 3) if se_ols[0] > 0 else None,
        "t_alpha_hac": _r(t_a_hac, 3) if t_a_hac is not None else None,
        "p_alpha_one_sided_hac": (_r(1.0 - _ncdf(float(t_a_hac)))
                                  if t_a_hac is not None else None),
        "beta": _r(beta, 4),
        "beta_se_hac": _r(se_hac[1]),
        "t_beta_minus_1_hac": (_r((beta - 1.0) / se_hac[1], 3)
                               if se_hac[1] > 0 else None),
        "r_squared": _r(1.0 - ssr / sst, 4) if sst > 0 else None,
        "hac_note": "Bartlett kernel, no dof inflation; OLS se uses n - 2",
    }


def _window_leg(daily: pd.Series, g: pd.DataFrame, months) -> tuple[pd.Series, dict]:
    """Compound a DAILY series over each book month's OWN (entry, maturity] window.

    The panel row labelled `2020-02` is the book entered 2020-02-21 and held into
    the -33.3% March. Reindexing a CALENDAR-month series onto those labels
    attaches February's rate to a March holding period, and `beta_matched`
    silently fillna(0)'s whatever fails to line up.
    """
    vals, missing = {}, []
    for m in months:
        if m not in g.index:
            missing.append(str(m))
            continue
        row = g.loc[m]
        if pd.isna(row["entry"]) or pd.isna(row["mat"]):
            missing.append(str(m))
            continue
        w = daily[(daily.index > pd.Timestamp(row["entry"]))
                  & (daily.index <= pd.Timestamp(row["mat"]))]
        if w.empty:
            missing.append(str(m))
            continue
        vals[m] = float((1.0 + w).prod() - 1.0)
    ser = pd.Series(vals, dtype="float64").reindex(months)
    note = {"months_built": int(ser.notna().sum()), "months_missing": missing,
            "mean_monthly": _r(float(ser.mean()), 6),
            "annualised_12x": _r(float(ser.mean()) * 12.0)}
    if ser.isna().any():
        note["declared"] = ("0.0 on the months that could not be built, and they are "
                            "named above -- never silently zero-filled")
        ser = ser.fillna(0.0)
    return ser.astype("float64"), note


def _month_windows(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("month")
              .agg(entry=("entry_date", "min"),
                   mat=("mat_date_1m", lambda s: s.dropna().mode().iloc[0]
                        if s.dropna().size else pd.NaT)))


def top_sets(df: pd.DataFrame, col: str, k: int, floor: float) -> dict:
    """The top-k permno set per month, under the SAME floor the book uses.

    This is the direct measure of "different errors": two selectors that hold the
    same names are one selector. Rebuilt here rather than pulled out of
    `evaluate.book` because that function returns weights, not sets, and asking
    it to return sets would change a sealed receipt's key set.
    """
    d = df[["month", "permno", col, "fwd_1m", "mkt_vw_1m", "log_dollar_vol_20d"]].dropna(
        subset=[col, "fwd_1m", "mkt_vw_1m"])
    d = d[np.expm1(d["log_dollar_vol_20d"].to_numpy()) >= floor]
    mo = d["month"].astype(str).str.replace("-", "", regex=False).astype("int64")
    tb = (d["permno"].astype("int64") * 2_654_435_761 + mo * 97 + 20260902) % 1_000_003
    d = d.assign(_tb=tb)
    out = {}
    for m, chunk in d.groupby("month", sort=True):
        sel = chunk.sort_values([col, "_tb"], ascending=[False, True]).head(k)
        out[m] = set(sel["permno"].astype("int64").tolist())
    return out


def overlap_block(a: dict, b: dict, k: int) -> dict:
    """Jaccard and raw overlap of the two selectors' monthly holdings."""
    common = sorted(set(a) & set(b))
    if not common:
        return {"verdict": "CANNOT DETERMINE", "why": "no common months"}
    jac, inter = [], []
    for m in common:
        sa, sb = a[m], b[m]
        u = len(sa | sb)
        jac.append(len(sa & sb) / u if u else np.nan)
        inter.append(len(sa & sb))
    return {
        "months": len(common),
        "k": k,
        "mean_names_in_common": _r(float(np.mean(inter)), 2),
        "mean_jaccard": _r(float(np.nanmean(jac)), 4),
        "min_names_in_common": int(np.min(inter)),
        "max_names_in_common": int(np.max(inter)),
        "expected_overlap_if_independent_draws_from_the_menu": (
            "not computed here -- the monthly menu size varies; see "
            "mean_names_in_common against k as the crude ruler"),
        "reading": (f"two selectors holding {np.mean(inter):.1f} of {k} names in common "
                    f"are {'largely the same book' if np.mean(inter) > k * 0.5 else 'holding substantially different books'}"),
    }


def run(*, verbose: bool = True) -> dict:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    day = date.today().isoformat()

    out: dict = {
        "job": "A1_shadow_grader",
        "lane": "A",
        "question": ("do lgbm_clf and nn_pre_causal make DIFFERENT errors? Graded by "
                     "ONE grader against the beta-matched benchmark (PRIMARY) and the "
                     "raw market (SECONDARY), with the paired monthly difference "
                     "between the two selectors as the PRIMARY SERIES."),
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
        "network_calls": 0,
        "day": day,
    }

    # ------------------------------------------------------------- heartbeat
    log("heartbeat ...")
    out["heartbeat"] = heartbeat(day)

    # ------------------------------------------------------- historical grade
    grade: dict = {"status": "NOT ATTEMPTED"}
    try:
        grade = historical_grade(log)
    except Exception as exc:                                            # noqa: BLE001
        grade = {"status": "ERROR",
                 "reasons": [f"{type(exc).__name__}: {exc}"],
                 "traceback": traceback.format_exc()}
    out["historical_grade"] = grade

    out["headline"] = _headline(out)
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    return out


def historical_grade(log) -> dict:
    from learner import benchmark as BM
    from learner import evaluate
    from learner import inference
    from learner import long_panel as LP
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B
    from scripts.weekend_lab_jobs import era_sign_table

    g: dict = {"status": "RUNNING"}
    g["memory_free_gb_before"] = W3B.free_gb()
    if not LP.LONG_TABLE.exists():
        return {"status": "SKIPPED",
                "reasons": [f"the long panel {LP.LONG_TABLE} is absent; nothing to grade. "
                            "This is a named reason, not a silent pass."]}

    log("  loading the floored universe ...")
    df, uni, fp = W3B.load_universe(verbose=False)
    note_input(LP.LONG_TABLE)
    g["training_universe"] = {k: uni[k] for k in
                             ("dollar_volume_floor_usd_per_day", "min_close_usd",
                              "rows_before", "rows_after", "share_kept", "months_after")}
    g["universe_fingerprint_sha256"] = fp

    if W3B_RECEIPT.exists():
        note_input(W3B_RECEIPT, sha=True)
        w3b = json.loads(W3B_RECEIPT.read_text(encoding="utf-8"))
        g["universe_fingerprint_matches_w3b"] = bool(
            fp == w3b.get("universe_fingerprint_sha256"))
        if not g["universe_fingerprint_matches_w3b"]:
            return {**g, "status": "REFUSED",
                    "reasons": [f"this universe is {fp[:16]} and W3b graded "
                                f"{str(w3b.get('universe_fingerprint_sha256'))[:16]}. A "
                                f"different population is a different question."]}
    else:
        g["universe_fingerprint_matches_w3b"] = "CANNOT DETERMINE (W3b receipt absent)"

    # ---- the predictions, off the stage parquets. REFUSE, never refit.
    years = list(range(N.FIRST_TEST_YEAR, N.LAST_TEST_YEAR + 1))
    seeds = [N.SEED_BASE + i for i in range(N.N_SEEDS)]
    try:
        for tag, scope in (("incumbents", W3B._scope(years, [])),
                           ("nn_pre_causal", W3B._scope(years, seeds))):
            block, _meta = W3B._read_stage(tag, fp, scope)
            for col in block.columns:
                df[col] = block[col].reindex(df.index).astype("float64")
            note_input(W3B._stage_path(tag))
            note_input(W3B.STAGE_DIR / f"w3b_meta_{tag}.json", sha=True)
    except SystemExit as exc:
        return {**g, "status": "REFUSED",
                "reasons": [str(exc),
                            "the stage predictions are the frozen vintage; refitting "
                            "them here would be a different experiment wearing the "
                            "same name. Retraining is ATTENDED."]}
    missing = [c for c in SELECTORS.values() if c not in df.columns]
    if missing:
        return {**g, "status": "REFUSED",
                "reasons": [f"stage files carry no column for {missing}"]}

    # ---- grade both selectors at both cost rates
    log("  grading both selectors ...")
    net, mkt, cells = {}, {}, {}
    for name, col in SELECTORS.items():
        for bps in COSTS:
            key = f"{name}|{int(bps)}bps"
            bk = evaluate.book(df, col, k=K, weight=WEIGHT, cost_bps=bps,
                               ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                               tradable_floor=N.TRADABLE_FLOOR_USD, return_series=True)
            ser = bk.pop("_series")
            cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
            net[key] = ser["net"].astype("float64")
            mkt[key] = ser["market"].astype("float64")
    g["cells_raw_market"] = cells

    months = net[f"lgbm_clf|10bps"].index
    g["n_months"] = int(len(months))
    g["window"] = [str(months[0]), str(months[-1])]

    # ---- the legs: rf and the pinned market TR, over each month's OWN window
    win = _month_windows(df)
    legs: dict = {}
    try:
        rf_d = BM.cash().returns.dropna().astype("float64")
        rf, rf_note = _window_leg(rf_d, win, months)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
        legs["risk_free"] = rf_note
    except Exception as exc:                                            # noqa: BLE001
        rf = pd.Series(0.0, index=months)
        legs["risk_free"] = {"available": False, "why": f"{type(exc).__name__}: {exc}",
                             "declared": "rf = 0; the SLOPE is unaffected, only the "
                                         "intercept's level moves"}
    try:
        pm_d = BM.pinned_market_total_return().returns.dropna().astype("float64")
        pmkt, pm_note = _window_leg(pm_d, win, months)
        pm_note["source"] = ("learner.benchmark.pinned_market_total_return() -- pinned "
                             "FF daily total-market return, OFFLINE")
        pm_note["why_not_spy"] = (
            "the mandate names SPY TR. benchmark.spy_total_return() fetches from "
            "yfinance and this lane is under a hard zero-network rule, so the pinned "
            "FF total market is used and is NEVER called SPY.")
        legs["pinned_market_tr"] = pm_note
    except Exception as exc:                                            # noqa: BLE001
        pmkt = None
        legs["pinned_market_tr"] = {"available": False,
                                    "why": f"{type(exc).__name__}: {exc}"}
    g["benchmark_legs"] = legs
    g["month_label_convention"] = (
        "a row labelled YYYY-MM is the book ENTERED on that month's entry_date and "
        "held to its 1m maturity; every leg is compounded over that same window.")

    # ---- per-selector: beta, beta-matched excess (PRIMARY), raw excess (SECONDARY)
    by_cell: dict = {}
    bm_excess: dict = {}
    raw_excess: dict = {}
    for key, n_ser in net.items():
        m_ser = mkt[key].reindex(n_ser.index)
        y = (n_ser - rf.reindex(n_ser.index)).astype("float64")
        x = (m_ser - rf.reindex(n_ser.index)).astype("float64")
        reg = ols_market_model(y, x)
        beta = reg.get("beta")
        if beta is None:
            by_cell[key] = {"verdict": "CANNOT DETERMINE", "regression": reg}
            continue
        bm = float(beta) * m_ser + (1.0 - float(beta)) * rf.reindex(n_ser.index)
        ex_bm = (n_ser - bm).dropna()
        ex_raw = (n_ser - m_ser).dropna()
        bm_excess[key] = ex_bm
        raw_excess[key] = ex_raw
        blk = {
            "PRIMARY_beta_matched": {
                "benchmark": f"{beta:g} x mkt_vw_1m + {1 - beta:g} x pinned_rf",
                "months": int(len(ex_bm)),
                "mean_monthly_pct": _r(float(ex_bm.mean()) * 100, 4),
                "annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
                "t_paired": _r(_t(ex_bm), 3),
                "months_ahead": _r(float((ex_bm > 0).mean()), 4),
            },
            "SECONDARY_raw_market": {
                "benchmark": "mkt_vw_1m (a 1.00x market leg)",
                "months": int(len(ex_raw)),
                "annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
                "t_paired": _r(_t(ex_raw), 3),
            },
            "market_regression": reg,
            "verdict": ("LOADING" if (reg.get("t_beta_minus_1_hac") or 0) > 2
                        and (reg.get("t_alpha_hac") or 0) < 2 else
                        "INTERCEPT" if (reg.get("t_alpha_hac") or 0) >= 2 else
                        "NEITHER SEPARATED"),
        }
        if pmkt is not None:
            ex_pm = (n_ser - pmkt.reindex(n_ser.index)).dropna()
            blk["SECONDARY_pinned_market_tr"] = {
                "benchmark": "pinned FF total market TR over the same windows "
                             "(the offline stand-in for SPY TR; NOT SPY)",
                "months": int(len(ex_pm)),
                "annualised_pct": _r(float(ex_pm.mean()) * 12 * 100, 3),
                "t_paired": _r(_t(ex_pm), 3),
            }
        by_cell[key] = blk
    g["by_cell"] = by_cell

    # ---- reproduction check against C1's published betas
    if C1_RECEIPT.exists():
        note_input(C1_RECEIPT, sha=True)
        c1 = json.loads(C1_RECEIPT.read_text(encoding="utf-8"))
        rep = {}
        for mine, theirs in (("lgbm_clf|10bps", "lgbm_clf|10bps"),
                             ("lgbm_clf|25bps", "lgbm_clf|25bps"),
                             ("nn_pre_causal|10bps", "nn_pre_causal_seedmean|10bps"),
                             ("nn_pre_causal|25bps", "nn_pre_causal_seedmean|25bps")):
            want = ((c1.get("by_cell") or {}).get(theirs) or {})
            wreg = want.get("A_market_regression") or {}
            wbm = want.get("B_beta_matched") or {}
            got = (by_cell.get(mine) or {}).get("market_regression") or {}
            gbm = (by_cell.get(mine) or {}).get("PRIMARY_beta_matched") or {}
            def _close(a, b, tol=5e-3):
                try:
                    return abs(float(a) - float(b)) <= tol
                except (TypeError, ValueError):
                    return False
            rep[mine] = {
                "c1_beta": wreg.get("beta"), "this_job_beta": got.get("beta"),
                "c1_annualised_beta_matched_excess_pct": (
                    None if wbm.get("annualised_excess_12x") is None
                    else round(float(wbm["annualised_excess_12x"]) * 100, 3)),
                "this_job_annualised_pct": gbm.get("annualised_pct"),
                "c1_t_paired": wbm.get("t_paired"),
                "this_job_t_paired": gbm.get("t_paired"),
                "c1_t_alpha_hac": wreg.get("t_alpha_hac"),
                "this_job_t_alpha_hac": got.get("t_alpha_hac"),
                "beta_matches": _close(wreg.get("beta"), got.get("beta")),
                "excess_matches": _close(
                    (wbm.get("annualised_excess_12x") or 0) * 100,
                    gbm.get("annualised_pct"), tol=0.01),
                "t_matches": _close(wbm.get("t_paired"), gbm.get("t_paired"), tol=0.01),
            }
        g["reproduces_C1"] = rep
        g["reproduces_C1_all"] = all(v["beta_matches"] and v["excess_matches"]
                                     and v["t_matches"] for v in rep.values())
        g["reproduces_C1_note"] = (
            "the BUILD doc quotes lgbm_clf at 't 0.349' and nn_pre_causal at 't 1.095'. "
            "Those are the HAC t on the CAPM INTERCEPT (`t_alpha_hac`), not the t on "
            "the beta-matched excess series (`t_paired`, 0.418 and 1.153). They are two "
            "statistics on the same number and both are carried here so nobody quotes "
            "one under the other's name.")

    # ---- THE PRIMARY SERIES: the paired difference between the two selectors
    log("  the paired difference ...")
    primary: dict = {}
    for bps in COSTS:
        kl, kn = f"lgbm_clf|{int(bps)}bps", f"nn_pre_causal|{int(bps)}bps"
        if kl not in bm_excess or kn not in bm_excess:
            continue
        common = bm_excess[kl].index.intersection(bm_excess[kn].index)
        d_bm = (bm_excess[kn].loc[common] - bm_excess[kl].loc[common]).astype("float64")
        d_net = (net[kn].loc[common] - net[kl].loc[common]).astype("float64")
        tb = _t(d_bm)
        blk = {
            "definition": ("D_t = (net_nn - beta_matched_nn) - (net_lgbm - "
                           "beta_matched_lgbm). PRIMARY because the two selectors carry "
                           "DIFFERENT betas: differencing the raw nets would compare a "
                           "1.33x market leg against a 1.18x one and call the extra "
                           "equity premium 'different errors'."),
            "months": int(len(d_bm)),
            "mean_monthly_pct": _r(float(d_bm.mean()) * 100, 4),
            "annualised_pct": _r(float(d_bm.mean()) * 12 * 100, 3),
            "t_paired": _r(tb, 3),
            "t_paired_hac_lag4": _r(evaluate.hac_t(d_bm, NW_LAG), 3),
            "p_one_sided": _r(1.0 - _ncdf(float(tb))) if tb is not None else None,
            "months_nn_ahead": _r(float((d_bm > 0).mean()), 4),
            "SECONDARY_raw_net_difference": {
                "definition": "net_nn - net_lgbm, no beta adjustment on either side",
                "annualised_pct": _r(float(d_net.mean()) * 12 * 100, 3),
                "t_paired": _r(_t(d_net), 3),
            },
            "era_table_on_the_PRIMARY_difference": era_sign_table(d_bm),
            "correlation_of_the_two_beta_matched_excesses": _r(
                float(bm_excess[kn].loc[common].corr(bm_excess[kl].loc[common])), 4),
            "correlation_of_the_two_net_series": _r(
                float(net[kn].loc[common].corr(net[kl].loc[common])), 4),
            "months_the_two_disagree_in_sign_of_excess": int(
                ((bm_excess[kn].loc[common] > 0) != (bm_excess[kl].loc[common] > 0)).sum()),
        }
        fam = {k: v for k, v in bm_excess.items()}
        blk["inference"] = inference.full_report(
            d_bm.to_numpy(), family=fam,
            n_trials=FAMILY_SEARCH_THAT_PRODUCED_THE_PREDICTIONS,
            paired_excess={"nn_pre_causal": bm_excess[kn].loc[common].to_numpy(),
                           "lgbm_clf": bm_excess[kl].loc[common].to_numpy()},
            seed=20260907)
        pw = blk["inference"].get("power") or {}
        mde = pw.get("mde_annual_excess_at_t_target")
        eff = abs(float(d_bm.mean()) * 12.0)
        blk["scope_aware_verdict"] = {
            "verdict": ("UNDERPOWERED, NOT NOISE" if (mde is not None and eff < float(mde))
                        else "SEPARATED FROM ZERO" if (tb is not None and tb >= 2.0)
                        else "NOISE (powered to see an effect this size and did not)"),
            "observed_effect_annual": _r(eff),
            "mde_annual_at_t_2": _r(mde),
            "years_of_tape_needed": pw.get("years_needed_to_detect_that_effect"),
            "scope": (f"251 months, 2004-01..2024-11, top-{K} {WEIGHT} books on the "
                      f"$3m/day-floored research panel. This says nothing about the "
                      f"pair's forward behaviour: neither selector has a forward "
                      f"vintage (see heartbeat)."),
        }
        blk["inference"]["family_note"] = (
            f"n_trials = {FAMILY_SEARCH_THAT_PRODUCED_THE_PREDICTIONS}: the cells the "
            f"W3b search that produced these predictions looked at. This job's own "
            f"family is {FAMILY_THIS_JOB} cells; both are declared and neither is the "
            f"convenient one alone.")
        primary[f"{int(bps)}bps"] = blk
    g["PRIMARY_paired_difference"] = primary

    # ---- family-max p over this job's own cells (Holm)
    ps = {}
    for key, ex in bm_excess.items():
        t = _t(ex)
        ps[key] = None if t is None else float(1.0 - _ncdf(t))
    for bps in COSTS:
        b = primary.get(f"{int(bps)}bps") or {}
        if b.get("p_one_sided") is not None:
            ps[f"paired_difference|{int(bps)}bps"] = float(b["p_one_sided"])
    ordered = sorted([(k, v) for k, v in ps.items() if v is not None], key=lambda kv: kv[1])
    n = len(ordered)
    holm, run_max = {}, 0.0
    for i, (k, p) in enumerate(ordered):
        adj = min(1.0, max(run_max, (n - i) * p))
        run_max = adj
        holm[k] = _r(adj)
    g["family"] = {
        "size_this_job": n,
        "family_min_p_one_sided": _r(ordered[0][1]) if ordered else None,
        "family_max_p_one_sided": _r(ordered[-1][1]) if ordered else None,
        "holm_adjusted": holm,
        "nothing_survives_holm_at_0_05": all(v is None or v > 0.05 for v in holm.values()),
    }

    # ---- the "different errors" question, answered on holdings
    log("  holdings overlap ...")
    sets = {name: top_sets(df, col, K, N.TRADABLE_FLOOR_USD)
            for name, col in SELECTORS.items()}
    g["different_errors"] = {
        "holdings_overlap": overlap_block(sets["lgbm_clf"], sets["nn_pre_causal"], K),
        "why_this_is_the_question": (
            "docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md: all ten arena books select "
            "on ONE signal. A second selector earns the name only if its ERRORS are "
            "different -- correlation of excesses and overlap of holdings are the two "
            "cheapest rulers, and both are reported here rather than a model card."),
    }

    g["memory_free_gb_after"] = W3B.free_gb()
    g["status"] = "OK"
    return g


def _headline(out: dict) -> str:
    hg = out.get("historical_grade") or {}
    hb = out.get("heartbeat") or {}
    l = (hb.get("lgbm_clf_daily_shadow") or {}).get("status")
    nn = (hb.get("nn_pre_causal_shadow") or {}).get("status")
    if hg.get("status") != "OK":
        return (f"HEARTBEAT ONLY. lgbm_clf daily shadow: {l}. nn_pre_causal: {nn}. "
                f"Historical grade {hg.get('status')}: {(hg.get('reasons') or ['-'])[0]}")
    p = (hg.get("PRIMARY_paired_difference") or {}).get("10bps") or {}
    ov = ((hg.get("different_errors") or {}).get("holdings_overlap") or {})
    return (f"PRIMARY (nn_pre_causal - lgbm_clf, beta-matched excess, 10 bps): "
            f"{p.get('annualised_pct')}%/yr at t {p.get('t_paired')} over "
            f"{p.get('months')} months; the two books hold "
            f"{ov.get('mean_names_in_common')} of {ov.get('k')} names in common "
            f"(corr of beta-matched excesses "
            f"{p.get('correlation_of_the_two_beta_matched_excesses')}). "
            f"Nightly: lgbm_clf {l}, nn_pre_causal {nn}.")


def write(rec: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rec["_provenance"] = {
        "sys_argv": list(sys.argv),
        "resolved_config": {
            "SELECTORS": SELECTORS, "COSTS": list(COSTS), "K": K, "WEIGHT": WEIGHT,
            "NW_LAG": NW_LAG, "FAMILY_THIS_JOB": FAMILY_THIS_JOB,
            "FAMILY_SEARCH": FAMILY_SEARCH_THAT_PRODUCED_THE_PREDICTIONS,
            "receipt": str(RECEIPT),
        },
        "_inputs_opened": _INPUTS,
        "inputs_note": ("every file this run OPENED, with size and mtime. Large "
                        "parquets are not hashed -- the universe fingerprint check "
                        "against W3b is the stronger guarantee and is reported "
                        "separately."),
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    rec["generated_utc"] = rec["_provenance"]["generated_utc"]
    RECEIPT.write_text(json.dumps(rec, indent=1, default=str),
                       encoding="utf-8", newline="\n")
    return RECEIPT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--heartbeat-only", action="store_true",
                    help="skip the historical grade; write the nightly heartbeat only")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    verbose = not a.quiet
    try:
        if a.heartbeat_only:
            rec = {"job": "A1_shadow_grader", "lane": "A", "licence": "PRODUCT_EXPERIMENT",
                   "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
                   "day": date.today().isoformat(),
                   "heartbeat": heartbeat(date.today().isoformat()),
                   "historical_grade": {"status": "SKIPPED",
                                        "reasons": ["--heartbeat-only was passed"]}}
            rec["headline"] = _headline(rec)
        else:
            rec = run(verbose=verbose)
    except Exception as exc:                                            # noqa: BLE001
        # A TRACEBACK IS A RECEIPT. A job that dies without one is a night with
        # no evidence, which is indistinguishable from a night that was never run.
        rec = {"job": "A1_shadow_grader", "lane": "A", "status": "CRASHED",
               "llm_spend_usd": 0.0, "llm_calls": 0,
               "error": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc(),
               "headline": f"CRASHED: {type(exc).__name__}: {exc}"}
    p = write(rec)
    print(f"\n{rec.get('headline')}\n-> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
