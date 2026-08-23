"""EVENT-RESPONSE-2 — surprise relative to what the options market already priced.

WHY THIS EXISTS
===============
`EVENT-RESPONSE-1` returned STOP: post-earnings drift is real (+7bps, t 2.66 at
one session) and **nothing ranked which events drift**. Its own diagnosis named
the most likely reason:

    `options_implied_move` is None through the entire g4 corpus, so "surprise"
    was measured against analyst consensus alone -- when the tradable quantity
    is `surprise MINUS what was already priced`.

`wrds_pull_stdopd_events` fixed that. This is the same design with the same
target and the same nine-arm structure; what changes is the central feature.

THE CENTRAL FEATURE
===================
`gap_vs_implied = |overnight_gap| / implied_move_1d`

Did the stock move more or less than the options market expected it to? A large
beat that moved the stock LESS than the straddle priced is a different event
from the same beat that moved it more, and analyst consensus cannot tell them
apart. This is the review's "surprise of surprise" in the most direct form the
data supports.

AND A CONFOUND CONTROL THAT CAME FREE
=====================================
A 2025 JFE result holds that much of the apparent stock-return predictability in
option-implied measures is explained by **stock borrow fees** — excluding
high-borrow names removes a large part of it. The roadmap promoted
`OPTIONS_BORROW_CONFOUND_v1` to a PRECONDITION of this work rather than a
follow-up.

It is computable here at no extra cost. By put-call parity ATM call and put
implied vols should agree; the residual `iv_put_minus_call_30d` is the classic
borrow/hard-to-borrow proxy. So the confound enters as a FEATURE and as a
declared slice, rather than as a caveat at the end.

WHAT IS STILL NOT AVAILABLE
===========================
**Skew, 25-delta, risk reversal, butterfly.** `stdopd` is ATM-only: 30-day calls
sit at a median delta of +0.523 and puts at -0.482. Those need `vsurfd`. Nothing
in this file computes them, and nothing should pretend to.

POINT-IN-TIME
=============
Option state is taken from the last session STRICTLY BEFORE the event's tradable
date. The target is unchanged from v1: `sign(gap) x excess return over the k
sessions strictly AFTER the event session`, entry at the event day's close,
because CRSP daily returns are close-to-close and including the event session
would put the gap inside the target it is signed by.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
STDOPD = REPO / "backend" / "data" / "optimus" / "wrds" / "stdopd_events"
OUT = REPO / "backend" / "data" / "optimus" / "event_response"

SPEC: dict = {
    "trial_id": "EVENT-RESPONSE-2",
    "licence": "PRODUCT_EXPERIMENT (screen — licenses building, never a claim)",
    "predecessor": "EVENT-RESPONSE-1 (STOP) — same target, same arms, new feature",
    "question": ("Does an earnings surprise measured against the OPTIONS "
                 "market's own expectation rank post-event drift, where a "
                 "surprise measured against analyst consensus did not?"),
    "central_feature": "gap_vs_implied = |overnight_gap| / implied_move_1d",
    "implied_move_1d": "atm_iv_30 * sqrt(1/252), from the session BEFORE the event",
    "borrow_confound": (
        "iv_put_minus_call_30d — the ATM put-call IV residual, which by "
        "put-call parity is a borrow/hard-to-borrow proxy. Entered as a "
        "FEATURE and as a declared slice, because a 2025 JFE result holds that "
        "much of option-implied return predictability is borrow fees. The "
        "roadmap made this a PRECONDITION of this work, not a follow-up."),
    "target": ("unchanged from v1: sign(gap) * cumulative excess return over "
               "the k sessions STRICTLY AFTER the event session"),
    "horizons_sessions": [1, 2, 5],
    "n_effective": "EVENT MONTHS (date blocks) — never events (CANON §58)",
    "split": "expanding-window by year; train < Y, test = Y, Y from 2012",
    "models": ["surprise_only", "ridge", "lightgbm"],
    "leakage_guard": ("feature_leakage_guard.assert_no_target_leakage runs "
                      "BEFORE any model is fitted"),
    "decision_rule": (
        "BUILD a selector iff an arm's mean monthly rank IC survives BH-FDR at "
        "q<=0.10 across every (model, horizon) arm AND beats the RIDGE "
        "baseline by more than one paired SE — identical to v1, so the two "
        "runs are comparable and the ONLY difference is the feature set."),
    "and_the_comparison_that_matters": (
        "v1's arms are re-run here on the SAME events that have option data, "
        "so 'the options feature helped' is a paired difference on one sample "
        "rather than two runs on different populations."),
    "cannot_provide": "skew / 25-delta / RR / butterfly — stdopd is ATM-only",
}


def spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:16]


def load_option_state() -> pd.DataFrame:
    """Per (secid, date): ATM IV at 30 and 60 days, both sides."""
    files = sorted(STDOPD.glob("stdopd_events_*.parquet"))
    if not files:
        sys.exit(f"REFUSED: no stdopd extract at {STDOPD}. Run "
                 f"`python -m scripts.wrds_pull_stdopd_events --pull 2006 2019`")
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    piv = (d.pivot_table(index=["secid", "date"], columns=["days", "cp_flag"],
                         values="impl_volatility", aggfunc="mean")
           .reset_index())
    piv.columns = ["secid", "date"] + [f"iv{int(a)}{b}" for a, b in
                                       piv.columns[2:]]
    for c in ("iv30C", "iv30P", "iv60C", "iv60P"):
        if c not in piv:
            piv[c] = np.nan
    piv["atm_iv_30"] = piv[["iv30C", "iv30P"]].mean(axis=1)
    piv["atm_iv_60"] = piv[["iv60C", "iv60P"]].mean(axis=1)
    # The event premium: a near-dated maturity containing the announcement is
    # priced richer than one that spreads it over twice the window.
    piv["iv_term_slope"] = piv["atm_iv_30"] - piv["atm_iv_60"]
    # Put-call parity says these agree. What is left is borrow.
    piv["iv_put_minus_call_30d"] = piv["iv30P"] - piv["iv30C"]
    piv["implied_move_1d"] = piv["atm_iv_30"] * np.sqrt(1.0 / 252.0)
    return piv[["secid", "date", "atm_iv_30", "atm_iv_60", "iv_term_slope",
                "iv_put_minus_call_30d", "implied_move_1d"]]


def attach_option_state(ev: pd.DataFrame, opt: pd.DataFrame) -> pd.DataFrame:
    """Join the LAST option state strictly BEFORE each event's tradable date."""
    from scripts.wrds_pull_stdopd_events import event_secids

    _, linked = event_secids()
    ev = ev.merge(linked[["event_id", "secid"]], on="event_id", how="inner")
    ev["secid"] = ev["secid"].astype("int64")
    opt = opt.copy()
    opt["secid"] = opt["secid"].astype("int64")

    ev = ev.sort_values("event_date")
    opt = opt.sort_values("date")
    # `allow_exact_matches=False` is the PIT clause: option state ON the event
    # date is contemporaneous with the open we are trading, not prior to it.
    j = pd.merge_asof(ev, opt, left_on="event_date", right_on="date",
                      by="secid", direction="backward",
                      allow_exact_matches=False,
                      tolerance=pd.Timedelta("7D"))
    return j


# ─────────────────────────────────────────────────────────── the frame

#: v1's features, unchanged, so the two runs differ ONLY by what is added.
BASE_FEATURES = [
    "numeric_surprise_pct", "surprise_scaled", "expectation_dispersion",
    "n_estimates", "pre_event_price_runup", "overnight_gap", "abs_gap",
    "gap_vs_runup", "dollar_volume_20d_log", "hl_range_20d", "amihud_20d_log",
    "revision_up", "revision_down", "disclosure_delay_days",
]

#: What the options market knew, and the borrow confound that comes with it.
OPTION_FEATURES = [
    "atm_iv_30", "iv_term_slope", "iv_put_minus_call_30d",
    "implied_move_1d", "gap_vs_implied", "surprise_vs_implied",
]


def _fit(model: str, cols: list[str], Xtr, ytr, Xte):
    """v1's fitters, but told WHICH columns it was given.

    v1 resolves `surprise_only` by looking up an index in its own module-level
    FEATURES list. Reusing it here means either passing the column list or
    reassigning that global mid-run — and a verdict that depends on a module
    global being restored correctly after every fit is a verdict waiting to be
    wrong. So the one model that needs the mapping gets it explicitly.
    """
    from scripts.event_response_v1 import _fit_predict

    if model == "surprise_only":
        return Xte[:, cols.index("surprise_scaled")]
    return _fit_predict(model, Xtr, ytr, Xte)


def build_frame() -> pd.DataFrame:
    from scripts.event_response_v1 import (SPEC as V1, build_frame as v1_frame,
                                           forward_returns, link_permno,
                                           load_events)

    ev = link_permno(load_events())
    y0 = int(ev["event_date"].dt.year.min())
    y1 = int(ev["event_date"].dt.year.max())
    px, _ = forward_returns(set(ev["permno"].unique()), y0, y1)
    fr = v1_frame(ev, px)                    # v1's features and targets, as-is

    opt = load_option_state()
    j = attach_option_state(fr, opt)

    # THE CENTRAL FEATURE. A move the options market already expected is not a
    # surprise, whatever the analysts thought.
    im = j["implied_move_1d"].replace(0, np.nan)
    j["gap_vs_implied"] = (j["overnight_gap"].abs() / im).clip(0, 20)
    j["surprise_vs_implied"] = (j["numeric_surprise_pct"] / im).clip(-20, 20)
    return j


def run() -> dict:
    from scipy import stats

    from backend.services import feature_leakage_guard as FLG
    from scripts.event_response_v1 import (SPEC as V1, _bh_fdr, _fit_predict,
                                           _rank_ic)

    print(f"spec_hash {spec_hash()}", flush=True)
    fr = build_frame()
    have = fr["atm_iv_30"].notna()
    print(f"  {len(fr):,} events, {have.sum():,} with option state "
          f"({have.mean():.1%})", flush=True)
    fr = fr[have].copy()
    if len(fr) < 5000:
        sys.exit(f"REFUSED: only {len(fr)} events carry option state — a screen "
                 f"on that is a statement about whichever names had options")

    feats = BASE_FEATURES + OPTION_FEATURES
    leak = FLG.assert_no_target_leakage(fr, features=feats, target="drift1",
                                        block="event_month")
    print(f"  leakage guard PASS over {leak['n_blocks']} blocks | "
          f"strongest {leak['ranked'][:3]}", flush=True)

    years = sorted(y for y in fr["event_date"].dt.year.unique() if y >= 2012)
    ics: dict[str, list] = {}
    months: dict[str, list] = {}
    # BOTH feature sets on the SAME events, so "options helped" is a paired
    # difference on one sample rather than two runs on two populations.
    sets = {"base": BASE_FEATURES, "with_options": feats}
    for k in SPEC["horizons_sessions"]:
        tgt = f"drift{k}"
        for sname, cols in sets.items():
            for model in SPEC["models"]:
                arm = f"{model}@{k}d[{sname}]"
                ics[arm], months[arm] = [], []
                for Y in years:
                    tr = fr[(fr["event_date"].dt.year < Y) & fr[tgt].notna()]
                    te = fr[(fr["event_date"].dt.year == Y) & fr[tgt].notna()]
                    if len(tr) < 2000 or len(te) < 200:
                        continue
                    try:
                        pred = _fit(model, cols, tr[cols].to_numpy(float),
                                    tr[tgt].to_numpy(),
                                    te[cols].to_numpy(float))
                    except Exception as e:                      # noqa: BLE001
                        print(f"    {arm} {Y}: {type(e).__name__}: {e}",
                              flush=True)
                        continue
                    t2 = te.assign(_p=pred)
                    for m, g in t2.groupby("event_month"):
                        ic = _rank_ic(g["_p"].to_numpy(), g[tgt].to_numpy())
                        if ic is not None:
                            ics[arm].append(ic)
                            months[arm].append(str(pd.Timestamp(m).date()))
                print(f"  {arm:34s} {len(ics[arm])} months", flush=True)

    results, pvals = {}, {}
    for arm, series in ics.items():
        if len(series) < 12:
            results[arm] = {"n_months": len(series), "status": "TOO_FEW_MONTHS"}
            continue
        a = np.array(series)
        mean, se = float(a.mean()), float(a.std(ddof=1) / np.sqrt(len(a)))
        t = mean / se if se else 0.0
        pv = float(2 * (1 - stats.t.cdf(abs(t), df=len(a) - 1)))
        results[arm] = {"n_months": len(a), "mean_ic": round(mean, 5),
                        "se": round(se, 5), "t": round(t, 3),
                        "p_two_sided": round(pv, 5),
                        "mde_80pct_power": round(2.80 * se, 5)}
        pvals[arm] = pv
    for arm, ok in _bh_fdr(pvals, 0.10).items():
        results[arm]["bh_fdr_survives"] = bool(ok)

    def paired(x, y):
        mx, my = dict(zip(months.get(x, []), ics.get(x, []))), \
                 dict(zip(months.get(y, []), ics.get(y, [])))
        common = sorted(set(mx) & set(my))
        if len(common) < 12:
            return None
        v = np.array([mx[m] - my[m] for m in common])
        se = float(v.std(ddof=1) / np.sqrt(len(v)))
        mean = float(v.mean())
        return {"n_months": len(v), "mean_diff": round(mean, 6),
                "se": round(se, 6), "t": round(mean / se, 3) if se else 0.0,
                "beats_by_more_than_1se": bool(mean > se)}

    comps = {}
    for k in SPEC["horizons_sessions"]:
        for model in SPEC["models"]:
            comps[f"options_helps_{model}@{k}d"] = paired(
                f"{model}@{k}d[with_options]", f"{model}@{k}d[base]")

    passing = [a for a, r in results.items()
               if r.get("bh_fdr_survives") and r.get("mean_ic", 0) > 0
               and "with_options" in a]
    helped = [k for k, v in comps.items() if v and v["beats_by_more_than_1se"]]
    verdict = ("BUILD" if passing and helped else
               "OPTIONS_HELP_ONLY" if helped else
               "SIGNAL_ONLY" if passing else "STOP")

    receipt = {
        "trial_id": SPEC["trial_id"], "spec_hash": spec_hash(), "spec": SPEC,
        "n_events_with_option_state": int(len(fr)),
        "n_event_months": int(fr["event_month"].nunique()),
        "n_effective": int(fr["event_month"].nunique()),
        "leakage_guard": leak,
        "results": results, "paired_options_vs_base": comps,
        "arms_passing": passing, "options_helped": helped,
        "verdict": verdict,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "event_response_v2_receipt.json").write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "spec"},
                     indent=2, default=str))
