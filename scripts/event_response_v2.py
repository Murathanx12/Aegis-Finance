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


#: AMENDMENT-1, declared 2026-08-24, BEFORE any of its numbers existed.
#: POST-HOC, in its own BH-FDR family, and it re-examines a verdict I already
#: reached -- which is exactly when declaring first matters most.
#:
#: WHAT IT QUESTIONS. v2 downgraded BUILD -> NOT_LICENSED_BORROW_CONFOUNDED
#: because excluding the top borrow quintile took drift1 from +0.0315 (t 3.19)
#: to +0.0151 (t 1.42). The receipt argued this was not a POWER artefact, and
#: that argument is sound: the point estimate halved while MDE80 moved only
#: 0.0276 -> 0.0297.
#:
#: But "not a power artefact" does not establish "therefore borrow". A
#: cross-sectional rank IC is not additive across subsamples, and trimming the
#: top quintile of ANY variable correlated with the signal restricts the
#: signal's own spread. That is RANGE RESTRICTION, and it was never ruled out.
#: The whole downgrade rests on attributing the drop to the borrow variable
#: specifically.
#:
#: THE DECISIVE CONTROL IS THE OPPOSITE TAIL. Excluding the LOWEST borrow
#: quintile removes the same amount of data, from the same variable, at the
#: other end. If the effect really lives in hard-to-borrow names, cutting the
#: cheap ones should leave the IC intact or raise it. If cutting EITHER tail
#: halves it, the drop is what tail-trimming does to a rank IC and the borrow
#: attribution is unproven.
#:
#: WHAT IS AND IS NOT AT STAKE. This cannot restore a BUILD. The cheap-to-borrow
#: arm needs 654 event months to detect its own point estimate at 80% power and
#: at most ~240 exist, so it can never clear a RESEARCH_CLAIM bar on obtainable
#: data. What is at stake is the REASON for the refusal, and the reason decides
#: the successor: if borrow, v3 models the fee as a cost; if range restriction,
#: the honest verdict is UNDERPOWERED and v3 is a forward paper book instead.
AMENDMENT_1: dict = {
    "amendment_id": "EVENT-RESPONSE-2/AMENDMENT-1",
    "status": "POST-HOC — declared before any of its numbers existed",
    "question": ("is the IC drop under top-borrow-quintile exclusion "
                 "attributable to BORROW, or is it what excluding a tail does "
                 "to a cross-sectional rank IC?"),
    "primary_control": ("exclude the BOTTOM borrow quintile — same variable, "
                        "same sample loss, opposite tail"),
    "supporting_controls": [
        "exclude a RANDOM 20% (isolates pure sample-size loss)",
        "exclude the top quintile of placebo variables unrelated to borrow",
    ],
    "decision_rule": (
        "The borrow attribution STANDS iff excluding the HIGH-borrow quintile "
        "costs materially more IC than excluding the LOW-borrow quintile — "
        "concretely, iff ic_excl_high < ic_excl_low by more than the paired SE "
        "of the difference, AND ic_excl_high sits below the placebo "
        "exclusions. Otherwise the drop is RANGE RESTRICTION, the verdict's "
        "REASON changes to UNDERPOWERED, and the successor changes with it."),
    "cannot_show": (
        "That the signal is tradable. The power arithmetic forecloses a "
        "RESEARCH_CLAIM either way; this decides the refusal's reason and "
        "therefore what v3 should be."),
    "placebos": ["pre_event_price_runup", "disclosure_delay_days",
                 "expectation_dispersion", "iv_term_slope"],
    "n_random_draws": 20,
}


def amendment_1_hash() -> str:
    return hashlib.sha256(
        json.dumps(AMENDMENT_1, sort_keys=True).encode()).hexdigest()[:16]


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
        # CANON 58: n_effective counts the DATE BLOCKS the estimate is actually
        # made of. The first version reported the frame's month count (168),
        # but every arm walks forward from 2012 and so is built from 96 months
        # -- the frame's earlier months are TRAINING, and training months are
        # not evidence. Reporting 168 overstated the evidence base by 75%.
        # Both numbers are kept, with the roles named, because the frame count
        # is still the right denominator for coverage questions.
        "n_event_months_in_frame": int(fr["event_month"].nunique()),
        "n_effective": int(min(
            (r["n_months"] for r in results.values() if "n_months" in r),
            default=0)),
        "n_effective_basis": (
            "evaluated months of the leanest arm; arms walk forward from 2012 "
            "so months before that are training, not evidence"),
        "leakage_guard": leak,
        "results": results, "paired_options_vs_base": comps,
        "arms_passing": passing, "options_helped": helped,
        "verdict": verdict,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "event_response_v2_receipt.json").write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt


def run_amendment_1(tgt: str = "drift1") -> dict:
    """Is the borrow drop BORROW, or is it tail-trimming?

    ONE MODEL, MANY EVALUATION POPULATIONS. The walk-forward fit is identical
    to the primary run and is done ONCE; the slices then change only WHICH
    events are in the cross-section when the monthly IC is taken. Re-fitting per
    slice would confound "trained on less" with "evaluated on a different
    population", and the question is entirely about the population.
    """
    from scipy import stats

    from scripts.event_response_v1 import _rank_ic

    print(f"spec_hash {spec_hash()}  amendment_1 {amendment_1_hash()}",
          flush=True)
    fr = build_frame()
    fr = fr[fr["atm_iv_30"].notna()].copy()
    cols = BASE_FEATURES + OPTION_FEATURES
    model = "lightgbm"

    years = sorted(y for y in fr["event_date"].dt.year.unique() if y >= 2012)
    preds = []
    for Y in years:
        tr = fr[(fr["event_date"].dt.year < Y) & fr[tgt].notna()]
        te = fr[(fr["event_date"].dt.year == Y) & fr[tgt].notna()]
        if len(tr) < 2000 or len(te) < 200:
            continue
        pred = _fit(model, cols, tr[cols].to_numpy(float),
                    tr[tgt].to_numpy(), te[cols].to_numpy(float))
        preds.append(te.assign(_p=pred))
    ev = pd.concat(preds, ignore_index=True)
    print(f"  {len(ev):,} evaluated events over "
          f"{ev['event_month'].nunique()} months", flush=True)

    def monthly(frame) -> dict[str, float]:
        out = {}
        for m, g in frame.groupby("event_month"):
            ic = _rank_ic(g["_p"].to_numpy(), g[tgt].to_numpy())
            if ic is not None:
                out[str(pd.Timestamp(m).date())] = ic
        return out

    def summarise(d: dict[str, float]) -> dict:
        a = np.array(list(d.values()))
        if len(a) < 12:
            return {"n_months": len(a), "status": "TOO_FEW_MONTHS"}
        se = float(a.std(ddof=1) / np.sqrt(len(a)))
        mean = float(a.mean())
        return {"n_months": len(a), "mean_ic": round(mean, 5),
                "se": round(se, 5), "t": round(mean / se, 3) if se else 0.0,
                "mde_80pct_power": round(2.80 * se, 5)}

    b = "iv_put_minus_call_30d"
    hi_cut = float(ev[b].quantile(0.80))
    lo_cut = float(ev[b].quantile(0.20))

    series = {"all": monthly(ev)}
    # THE PRIMARY CONTROL: same variable, same 20%, opposite tail.
    series["excl_high_borrow"] = monthly(ev[ev[b] <= hi_cut])
    series["excl_low_borrow"] = monthly(ev[ev[b] >= lo_cut])

    # Pure sample-size loss, no range restriction at all.
    rng = np.random.default_rng(20260824)
    rand_ics = []
    for i in range(int(AMENDMENT_1["n_random_draws"])):
        keep = rng.random(len(ev)) >= 0.20
        rand_ics.append(summarise(monthly(ev[keep])).get("mean_ic"))
    rand_ics = [x for x in rand_ics if x is not None]

    # Other variables' top quintiles, to see what tail-trimming costs in
    # general.
    placebo = {}
    for v in AMENDMENT_1["placebos"]:
        if v not in ev.columns or ev[v].notna().sum() < 1000:
            placebo[v] = {"status": "UNAVAILABLE"}
            continue
        cut = float(ev[v].quantile(0.80))
        placebo[v] = summarise(monthly(ev[ev[v] <= cut]))

    def paired(x, y) -> dict | None:
        mx, my = series[x], series[y]
        common = sorted(set(mx) & set(my))
        if len(common) < 12:
            return None
        d = np.array([mx[m] - my[m] for m in common])
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        mean = float(d.mean())
        return {"n_months": len(d), "mean_diff": round(mean, 6),
                "se": round(se, 6), "t": round(mean / se, 3) if se else 0.0,
                "p": round(float(2 * (1 - stats.t.cdf(abs(mean / se),
                                                      df=len(d) - 1))), 4)
                if se else 1.0}

    summary = {k: summarise(v) for k, v in series.items()}
    hi = summary["excl_high_borrow"].get("mean_ic")
    lo = summary["excl_low_borrow"].get("mean_ic")
    diff = paired("excl_high_borrow", "excl_low_borrow")

    borrow_specific = bool(
        diff and hi is not None and lo is not None
        and (lo - hi) > diff["se"]
        and (not rand_ics or hi < float(np.percentile(rand_ics, 20))))

    verdict = ("BORROW_ATTRIBUTION_STANDS" if borrow_specific
               else "BORROW_ATTRIBUTION_NOT_ESTABLISHED")

    receipt = {
        "amendment_id": AMENDMENT_1["amendment_id"],
        "amendment_hash": amendment_1_hash(),
        "parent_spec_hash": spec_hash(),
        "declared_before_any_number_existed": True,
        "target": tgt, "model": model,
        "n_events": int(len(ev)),
        "n_effective": int(ev["event_month"].nunique()),
        "borrow_proxy": b,
        "cuts": {"top_quintile_at": round(hi_cut, 5),
                 "bottom_quintile_at": round(lo_cut, 5)},
        "slices": summary,
        "excl_high_vs_excl_low": diff,
        "random_20pct_exclusions": {
            "n_draws": len(rand_ics),
            "mean_ic_mean": round(float(np.mean(rand_ics)), 5)
            if rand_ics else None,
            "mean_ic_p20": round(float(np.percentile(rand_ics, 20)), 5)
            if rand_ics else None,
            "mean_ic_min": round(float(np.min(rand_ics)), 5)
            if rand_ics else None,
        },
        "placebo_top_quintile_exclusions": placebo,
        "decision_rule": AMENDMENT_1["decision_rule"],
        "verdict": verdict,
        "what_this_changes": (
            "The REASON for v2's refusal, and therefore what v3 should be. It "
            "cannot restore a BUILD: the cheap-to-borrow arm needs ~654 event "
            "months to detect its own point estimate at 80% power and at most "
            "~240 are obtainable."),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "" if tgt == "drift1" else f"_{tgt}"
    (OUT / f"event_response_v2_amendment1_receipt{suffix}.json").write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    if "--amendment-1" in sys.argv:
        _t = next((a.split("=", 1)[1] for a in sys.argv
                   if a.startswith("--target=")), "drift1")
        r = run_amendment_1(_t)
        print(json.dumps(r, indent=2, default=str))
        raise SystemExit(0)
    r = run()
    print(json.dumps({k: v for k, v in r.items() if k != "spec"},
                     indent=2, default=str))
