"""C's TWO FALSIFIERS — the test Book C's own first read named as its next_test.

WHY THIS JOB EXISTS
===================
`B_first_books_replay` run 1 (2026-09-12) read the disposition-overhang
conditioner at **+0.3978%/month** over 395 monthly blocks, NW lag-2 t 2.1283,
p 0.0333 — which does not survive the family's Holm block (alpha 0.016667) and
is below the book's own declared effect of 1.00%/month, so the first read
stands at CONDITIONAL. TRIAL-DRAFT-C §5 says that verdict is **not the end of
the question**: two falsifiers close the book whatever the primary metric did,
and neither had been run.

  (a) **the sign-flip placebo.** Frazzini (JF 2006) reports ~0 for the
      sign-flipped cell — long good-news/large-LOSS, short bad-news/large-GAIN.
      If our flipped cell ALSO pays, what we measured is drift (momentum again)
      and not the disposition effect, and §5 closes the book as FAILED_VARIANT.
  (b) **the momentum orthogonalisation.** Grinblatt-Han (JFE 2005) claim
      overhang SUBSUMES intermediate-horizon momentum: with overhang on the
      right-hand side, momentum disappears. If momentum SURVIVES here, the
      conditioner was momentum in costume, and §5 closes the book on that
      clause alone.

Either clause fires on its own. `CONDITIONAL` stands only if BOTH falsifiers
pass, which is why this job's verdict can only ever lower the book's standing
and never raise it.

AND THE READ IS THE REGISTERED ONE, WHICH RUN 1'S WAS NOT
=========================================================
Run 1 computed a name's overhang as soon as it carried **24** months of history
while passing a **60**-month lookback, so every name's first 36 overhangs — and
the entire 1990-1994 stretch, the panel starting in 1990 — came off a TRUNCATED
reference-price window. TRIAL-DRAFT-C §2 freezes T = 1260 sessions and §4
registers `slice_period 1995-01-01 .. 2024-12-31` precisely because the first
five years are warm-up, and the per-book receipt says `confirm_slice
1995-2024`. Its pooled 395 blocks and its 1990-1999 era included them anyway.

So this job runs the REGISTERED construction: a full 60-month window
(`min_history=60`) and a read that starts 1995-01. It re-reports Book C's own
PRIMARY metric under it, labelled `primary_registered_construction`, beside the
two falsifiers — that is the registered read, not a new test, and it is what
the verdict is taken against. Run 1's number is carried on the same receipt so
the difference is visible rather than quietly replacing it.

THE CONSTRUCTION IS IMPORTED, NOT RETYPED
=========================================
Every leg here is built from `night_first_books_replay.book_c_inputs` — the
same event-sign sets and the same Grinblatt-Han overhang series the book
itself traded — and run through the same `run_monthly` engine against the same
`unconditioned_reaction_book_v0` twin. A placebo built by a second
implementation of the same recursion is not a placebo; it is a different book
that happens to share a name.

The ONE thing that differs from Book C is the conditioning sign, and it differs
in `book_signals.overhang_conditioned_ranks(..., side="bottom")`, which the
book's own call does not pass.

WHAT IT MAY NOT DO
==================
* It reports no LEVEL as measured: the cost ruler is still the interim flat
  25 bps per side (`flat_25bps_pending_5c`), and both legs of every comparison
  here pay it, so only DIFFERENCES are read.
* It adds nothing to the family's multiplicity budget. `NIGHT_JOB_BOOKS_2026_09`
  declared FOUR primary tests and these are not among them: a falsifier is a
  registered TRIGGER, and the family's Holm block from run 1 is carried onto
  this receipt unchanged rather than recomputed over six legs.
* It cannot promote anything. §5's `PRODUCT_PROMISING` also needs the primary
  metric at 1.00%/month, which run 1 did not deliver.

    python -m scripts.night_factory_jobs C_falsifiers --smoke
    python -m scripts.night_factory_jobs C_falsifiers

THE TIME BOX, PROJECTED FROM A MEASURED RUN
===========================================
Run 1 of the whole replay took **829.3 s** for four books, of which Book C is
one monthly pass plus the overhang recursion over 420 months x 18,684 permnos,
and Book B's wide daily frame (which this job never builds) was the memory
peak. This job runs the panel load once, the overhang recursion once, TWO
monthly passes and one cross-sectional regression per month.

MEASURED here: the smoke pass (2014-2024, 132 months x 200 names, read from
2019-01) took **5.3 s** end to end. The full pass is 420 months over roughly
18,700 permnos, and both the recursion and the monthly passes scale with
month x name, so the projection is **10-25 minutes** -- inside the 60-minute
default box, but not by so much that a reader should trust the default without
looking. A job killed at the box writes no receipt at all (2026-09-10, G3 at
generation 340).
"""

from __future__ import annotations

import logging
from pathlib import Path

from scripts.night_first_books_replay import (
    CGO_LOOKBACK_MONTHS,
    COST_BPS_PER_SIDE,
    COST_CURVE,
    FAMILY,
    FULL_END,
    FULL_START,
    MIN_CONDITIONED_NAMES,
    SMOKE_NAMES,
    BookCInputsUnavailable,
    book_c_inputs,
    book_c_selectors,
    by_era,
    eligible,
    find_run_receipt,
    load_monthly_panel,
    names_with_sign,
    newey_west_t,
    run_monthly,
    two_sided_p,
)

logger = logging.getLogger("c_falsifiers")

JOB = "C_falsifiers"
BOOK = "disposition_overhang_conditioner_v0"
BOOK_ID = "book:a82e6e453c14c241"
PREREG = "TRIAL-DRAFT-C-disposition-overhang-conditioner-v0 (UNSIGNED)"

#: Frozen with the book: k, the tercile cut and the seed are Book C's own.
#: The seed is inert on these legs (both twins are NAMED selectors, so no
#: random draw happens) and is carried anyway, because a receipt that omits an
#: unused seed is indistinguishable from one that used a different seed.
K = 30
SEED = 0xA82E

#: `mom_12_1` in months, on the repo's own convention
#: (`portfolio_farm.signals.mom_12_1` is t-252 to t-21): the eleven months
#: ending ONE month before the formation close. The skipped month is skipped
#: because short-horizon winner-chasing is a Holm-surviving ANTI-signal in this
#: repository's own results, not because a textbook says 12-1.
MOM_MONTHS = 11
MOM_SKIP = 1

#: THE REGISTERED CONSTRUCTION. `min_history == lookback` is a FULL
#: reference-price window; `read_start` is TRIAL-DRAFT-C §4's own
#: `slice_period` start, which exists because the first five years of a
#: 1990-start panel are warm-up.
REGISTERED_MIN_HISTORY = CGO_LOOKBACK_MONTHS
REGISTERED_READ_START = "1995-01"

#: The smoke window is TEN YEARS, not the replay's three, because a 36-month
#: panel cannot carry a 60-month history and a smoke run under a construction
#: the job does not use proves the wrong thing.
SMOKE_START, SMOKE_END, SMOKE_READ_START = 2014, 2024, "2019-01"

#: A cross-sectional regression over fewer names than this is a regression on
#: the survivors, not on the market. Same spirit as `si_turnover_composite`'s
#: own `min_names`, and larger than the conditioner's 6 because a two-regressor
#: fit needs more room than a tercile cut.
MIN_REGRESSION_NAMES = 20

#: |t| at or above which a payoff is called alive. TRIAL-DRAFT-C §5 states the
#: threshold for the primary metric as 2.0 and reads both falsifiers against
#: "indistinguishable from 0" / "dies"; 2.0 is that line, and it is written
#: once here rather than four times below.
T_ALIVE = 2.0


# --------------------------------------------------------------------------
# (a) THE SIGN-FLIP PLACEBO


def sign_flip_selectors(inputs: dict) -> dict:
    """Book C's construction with the CONDITIONING SIGN FLIPPED, and nothing else.

    `good_loss` is the long leg Frazzini's placebo names: good news, large
    unrealised LOSS — the book's own eligible set, cut at the OTHER end of the
    same overhang distribution and ranked most-negative-first, which is the
    exact mirror of the book's most-positive-first.

    `bad_gain` is the short leg: bad news, large unrealised GAIN. A name whose
    month carries contradictory IBES rows is in both `good` and `bad`; it is
    excluded from the bad-news leg and counted, because a "short bad news" leg
    holding names the long leg calls good news is not the placebo.
    """
    from backend.services import book_signals as BS

    good = inputs["good"]
    bad = inputs["bad"]
    cgo_by_month = inputs["cgo_by_month"]

    def _cgo_for(pool, ym, wanted, excluded=None):
        names = set(names_with_sign(pool, ym, wanted))
        if excluded is not None:
            names -= set(names_with_sign(pool, ym, excluded))
        return {n: v for n, v in (cgo_by_month.get(ym) or {}).items() if n in names}

    def select_good_loss(pool, ym):
        cgo = _cgo_for(pool, ym, good)
        if len(cgo) < MIN_CONDITIONED_NAMES:
            return []
        try:
            bottom = BS.overhang_conditioned_ranks(cgo, {n: 1.0 for n in cgo},
                                                   side="bottom")
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(bottom.items(), key=lambda kv: kv[1])]

    def select_bad_gain(pool, ym):
        cgo = _cgo_for(pool, ym, bad, excluded=good)
        if len(cgo) < MIN_CONDITIONED_NAMES:
            return []
        try:
            top = BS.overhang_conditioned_ranks(cgo, {n: 1.0 for n in cgo})
        except BS.SignalUnavailable:
            return []
        return [p for p, _ in sorted(top.items(), key=lambda kv: -kv[1])]

    return {"good_loss": select_good_loss, "bad_gain": select_bad_gain}


def run_sign_flip_placebo(panel, inputs: dict, *, k: int = K,
                          seed: int = SEED) -> dict:
    """Both shapes of the placebo, and which of them DECIDES.

    `vs_unconditioned` is the deciding leg: it is Book C's own comparison with
    one thing changed, so it is directly comparable to the +0.3978%/month the
    book reported, and it is what §5's "the sign-flip placebo ALSO pays" means.

    `long_short` is the literature's own shape (long good-news/large-loss,
    short bad-news/large-gain, which Frazzini reports at ~0). It is reported
    beside the deciding leg and decides nothing: its short leg is a different
    universe, and reading a verdict off it would silently swap the comparator.
    """
    flip = sign_flip_selectors(inputs)
    book = book_c_selectors(inputs)
    vs_unc = run_monthly(panel, flip["good_loss"], k=k, seed=seed,
                         label="disposition_overhang_placebo_v0",
                         twin="unconditioned_reaction_book_v0",
                         twin_select=book["unconditioned"])
    ls = run_monthly(panel, flip["good_loss"], k=k, seed=seed,
                     label="frazzini_sign_flip_long_short",
                     twin="bad_news_large_gain_v0",
                     twin_select=flip["bad_gain"])
    mean = vs_unc.get("mean_excess_net_monthly")
    t = vs_unc.get("nw_lag2_t")
    pays = bool(mean is not None and mean > 0 and t is not None and t >= T_ALIVE)
    return {
        "falsifier": "sign_flip_placebo",
        "registered_as": ("TRIAL-DRAFT-C §3 'Reported, never deciding' lists it "
                          "and §5 makes it a FAILED_VARIANT trigger: 'the "
                          "sign-flip placebo ALSO pays (it is drift, i.e. "
                          "momentum again, not disposition)'"),
        "construction": ("Book C's eligible set and Book C's overhang series, "
                         "cut at the BOTTOM tercile instead of the top and "
                         "ranked most-negative-first. Nothing else moves: same "
                         "k, same monthly engine, same cost ruler, same twin."),
        "deciding_leg": "vs_unconditioned",
        "vs_unconditioned": {k2: v for k2, v in vs_unc.items()
                             if k2 not in ("blocks", "excess")},
        "vs_unconditioned_by_era": by_era(vs_unc),
        "long_short": {k2: v for k2, v in ls.items()
                       if k2 not in ("blocks", "excess")},
        "long_short_by_era": by_era(ls),
        "long_short_note": ("the literature's own shape, REPORTED. Frazzini "
                            "reports ~0 for it. It decides nothing here "
                            "because its comparator is a different universe "
                            "(bad-news names) and the book's registered "
                            "comparator is the unconditioned reaction book."),
        "t_alive": T_ALIVE,
        "placebo_pays": pays,
        "reading": (
            f"the placebo {'PAYS' if pays else 'does not pay'}: "
            f"{'' if mean is None else f'{mean:+.6f}'}/month vs the "
            f"unconditioned book at NW lag-2 t "
            f"{'n/a' if t is None else f'{t:.4f}'} over "
            f"{vs_unc.get('n_blocks')} blocks. §5 fires on a placebo that pays "
            f"(positive AND |t| >= {T_ALIVE}); a placebo indistinguishable "
            f"from 0 is what the book needs and is not by itself evidence FOR "
            f"the book."),
    }


# --------------------------------------------------------------------------
# (b) THE MOMENTUM ORTHOGONALISATION


def momentum_overhang_rows(panel, cgo_by_month: dict):
    """One row per (eligible name, month) with `mom`, `cgo` and NEXT month's return.

    `mom` is the eleven-month total return ending one month before the
    formation close, so the month the pick is made in is never inside the
    feature AND never inside the outcome. `cgo` is the book's own overhang for
    that month. The universe is `eligible()` — the same $3M/$5 corner the book
    selects in, because a regression run on a wider universe than the book
    answers a question about a different market.
    """
    import numpy as np
    import pandas as pd

    wide = panel.pivot_table(index="ym", columns="permno", values="ret_m",
                             aggfunc="last").sort_index()
    lg = np.log1p(wide.astype(float))
    # rolling(MOM_MONTHS) at row t covers t-10..t; shift(MOM_SKIP) makes it
    # t-11..t-1, which is the repo's t-252-to-t-21 in monthly resolution.
    mom = np.expm1(lg.rolling(MOM_MONTHS).sum().shift(MOM_SKIP))
    months = list(wide.index)
    by_month = {ym: g for ym, g in panel.groupby("ym", sort=False)}
    rows = []
    for i in range(len(months) - 1):
        ym, nxt = months[i], months[i + 1]
        pool = eligible(by_month[ym])
        if pool.empty:
            continue
        cgo = cgo_by_month.get(ym) or {}
        if not cgo:
            continue
        nf = by_month.get(nxt)
        if nf is None:
            continue
        fwd = dict(zip(nf["permno"], nf["ret_m"]))
        mrow = mom.loc[ym] if ym in mom.index else None
        if mrow is None:
            continue
        for pn in pool["permno"]:
            pn = int(pn)
            m = mrow.get(pn, np.nan)
            c = cgo.get(pn, np.nan)
            y = fwd.get(pn, np.nan)
            if not (np.isfinite(m) and np.isfinite(c) and np.isfinite(y)):
                continue
            rows.append({"ym": str(ym), "permno": pn, "mom": float(m),
                         "cgo": float(c), "fwd": float(y)})
    return pd.DataFrame(rows, columns=["ym", "permno", "mom", "cgo", "fwd"])


def _z(a):
    import numpy as np

    sd = float(np.std(a))
    if not np.isfinite(sd) or sd <= 0:
        return None
    return (a - float(np.mean(a))) / sd


def fama_macbeth_orthogonalisation(rows, *, min_names: int = MIN_REGRESSION_NAMES) -> dict:
    """Momentum and overhang, raw and residualised, priced month by month.

    Each month the two variables are standardised in the cross-section, then
    each is regressed on the other and the RESIDUAL re-standardised, so every
    slope below is a payoff per one cross-sectional standard deviation and the
    four numbers are on one ruler. The slope of next month's return on each
    variable is collected per month and the series carries a Newey-West lag-2 t
    over DATE BLOCKS (canon §58: names inside a month share the market).

    Frisch-Waugh says the bivariate slope on `mom` equals the univariate slope
    on `mom` residualised against `cgo`, up to the residual's scale. Both are
    computed anyway and the receipt prints both: an arithmetic identity that is
    asserted rather than checked is how a sign error survives a review.
    """
    import numpy as np

    slopes = {"raw_mom": [], "raw_cgo": [], "resid_mom": [], "resid_cgo": [],
              "bivariate_mom": [], "bivariate_cgo": []}
    rhos, blocks, n_names = [], [], []
    skipped = {"too_few_names": 0, "no_dispersion": 0, "collinear": 0}
    if len(rows) == 0:
        return {"n_blocks": 0, "refused": "no (name, month) row carried both "
                "a momentum and an overhang value"}
    for ym, g in rows.groupby("ym", sort=True):
        if len(g) < int(min_names):
            skipped["too_few_names"] += 1
            continue
        x = _z(g["mom"].to_numpy(dtype=float))
        c = _z(g["cgo"].to_numpy(dtype=float))
        if x is None or c is None:
            skipped["no_dispersion"] += 1
            continue
        y = g["fwd"].to_numpy(dtype=float)
        y = y - float(np.mean(y))
        rho = float(np.mean(x * c))
        if abs(rho) > 0.999:
            skipped["collinear"] += 1
            continue
        rm, rc = _z(x - rho * c), _z(c - rho * x)
        if rm is None or rc is None:
            skipped["no_dispersion"] += 1
            continue
        det = 1.0 - rho * rho
        bx, bc = float(np.mean(y * x)), float(np.mean(y * c))
        slopes["raw_mom"].append(bx)
        slopes["raw_cgo"].append(bc)
        slopes["resid_mom"].append(float(np.mean(y * rm)))
        slopes["resid_cgo"].append(float(np.mean(y * rc)))
        slopes["bivariate_mom"].append((bx - rho * bc) / det)
        slopes["bivariate_cgo"].append((bc - rho * bx) / det)
        rhos.append(rho)
        blocks.append(str(ym))
        n_names.append(int(len(g)))

    def _leg(key):
        s = slopes[key]
        t = newey_west_t(s)
        return {"mean_monthly_slope": (round(float(np.mean(s)), 6) if s else None),
                "nw_lag2_t": (round(t, 4) if t is not None else None),
                "p_two_sided": (round(two_sided_p(t), 6) if t is not None else None),
                "n_blocks": len(s)}

    out = {"n_blocks": len(blocks),
           "median_names_per_block": (int(np.median(n_names)) if n_names else 0),
           "mean_cross_sectional_corr_mom_cgo":
               (round(float(np.mean(rhos)), 4) if rhos else None),
           "skipped_months": skipped,
           "units": ("every slope is the next month's return per ONE "
                     "cross-sectional sd of the regressor, and every residual "
                     "is re-standardised so the four legs share that ruler"),
           "blocks": blocks}
    for key in slopes:
        out[key] = _leg(key)
    return out


def read_momentum_verdict(fm: dict) -> dict:
    """The §5 clause, applied to the orthogonalisation's own numbers."""
    if fm.get("n_blocks", 0) < 3:
        return {"momentum_survives": None,
                "verdict": "CANNOT_DETERMINE",
                "why": (f"{fm.get('n_blocks', 0)} usable monthly blocks; a "
                        f"Newey-West t over fewer than 3 is not a t. "
                        f"{fm.get('refused') or ''}".strip())}
    t_res_mom = (fm.get("resid_mom") or {}).get("nw_lag2_t")
    t_res_cgo = (fm.get("resid_cgo") or {}).get("nw_lag2_t")
    t_raw_mom = (fm.get("raw_mom") or {}).get("nw_lag2_t")
    survives = bool(t_res_mom is not None and abs(t_res_mom) >= T_ALIVE)
    cgo_survives = bool(t_res_cgo is not None and abs(t_res_cgo) >= T_ALIVE)
    raw_alive = bool(t_raw_mom is not None and abs(t_raw_mom) >= T_ALIVE)
    if not raw_alive:
        # 2026-09-13, found on run 1 (raw t 0.15): momentum was not priced on
        # these rows BEFORE overhang entered, so "momentum dies" would be
        # vacuous. Two readings, both carried. Grinblatt-Han's literal claim
        # (overhang SUBSUMES momentum) cannot be tested -- there is nothing to
        # subsume. The clause's PURPOSE ("it was momentum in costume") is
        # answered: a payoff momentum does not earn on these rows is not
        # momentum's, so the FAILED_VARIANT clause does not fire. Neither
        # reading is a pass of the subsumption test, and the receipt says so.
        return {
            "momentum_survives": False,
            "overhang_survives": cgo_survives,
            "subsumption_testable": False,
            "t_raw_mom": t_raw_mom, "t_resid_mom": t_res_mom,
            "t_resid_cgo": t_res_cgo,
            "verdict": "MOMENTUM_NOT_ALIVE",
            "why": (
                f"raw 12-1 momentum carries t {t_raw_mom} on the book's own "
                f"rows, below the |t| >= {T_ALIVE} line, BEFORE overhang enters "
                f"(after: t {t_res_mom}). Grinblatt-Han's subsumption claim is "
                f"untestable here -- nothing to subsume -- so this is NOT a pass "
                f"of that test. The §5 clause's purpose, 'it was momentum in "
                f"costume', is answered: momentum earns nothing on these rows, "
                f"so the book's excess is not momentum's, and the FAILED_VARIANT "
                f"clause does not fire. Overhang's own residual payoff carries "
                f"t {t_res_cgo}."),
        }
    return {
        "subsumption_testable": True,
        "momentum_survives": survives,
        "overhang_survives": cgo_survives,
        "t_raw_mom": t_raw_mom, "t_resid_mom": t_res_mom,
        "t_resid_cgo": t_res_cgo,
        "verdict": ("MOMENTUM_SURVIVES" if survives else "MOMENTUM_DIES"),
        "why": (
            f"with overhang on the right-hand side momentum's payoff carries "
            f"t {t_res_mom} against the |t| >= {T_ALIVE} line "
            f"(raw, before orthogonalisation: t {t_raw_mom}); overhang's own "
            f"residual payoff carries t {t_res_cgo}. Grinblatt-Han's claim is "
            f"that momentum DISAPPEARS here; TRIAL-DRAFT-C §5 closes the book "
            f"as FAILED_VARIANT if it does not."),
    }


# --------------------------------------------------------------------------
# the registered read window, and the January split


def registered_read_panel(panel, inputs: dict, *, read_start: str):
    """`panel` restricted to the months the registered construction may read.

    Two cuts, and they are different cuts. `read_start` is the registration's
    own `slice_period` start; the overhang's own first computable month is
    where a 60-month window first exists. The read begins at the LATER of the
    two, and the receipt prints both so a shortened smoke window cannot be
    mistaken for the registered one.
    """
    import pandas as pd

    have = sorted(ym for ym, d in (inputs.get("cgo_by_month") or {}).items() if d)
    first_cgo = have[0] if have else None
    start = pd.Period(read_start, freq="M")
    if first_cgo is not None and first_cgo > start:
        start = first_cgo
    cut = panel[panel["ym"] >= start]
    return cut.reset_index(drop=True), str(start), (
        str(first_cgo) if first_cgo is not None else None)


def january_split(result: dict) -> dict:
    """January vs February-December, on a result's own block series.

    UNREGISTERED DIAGNOSTIC. Grinblatt-Han's Table II has the overhang
    coefficient FLIPPING SIGN in January, and our block series carries the
    month for free, so the split costs nothing and is worth looking at. No
    decision rule is attached to it, it is not in the family's multiplicity
    budget, and nothing in TRIAL-DRAFT-C §5 turns on it. If it ever becomes a
    reason to do anything, that is a new registration.
    """
    import numpy as np
    import pandas as pd

    blocks, excess = result.get("blocks") or [], result.get("excess") or []
    if not blocks:
        return {"status": "no block series"}
    jan, rest = [], []
    for b, e in zip(blocks, excess):
        (jan if pd.Period(b, freq="M").month == 1 else rest).append(float(e))

    def _leg(v):
        t = newey_west_t(v) if len(v) >= 3 else None
        return {"n_blocks": len(v),
                "mean_excess_net_monthly": (round(float(np.mean(v)), 6) if v else None),
                "nw_lag2_t": (round(t, 4) if t is not None else None)}

    out = {"status": "UNREGISTERED_DIAGNOSTIC",
           "january": _leg(jan), "february_to_december": _leg(rest)}
    if jan and rest:
        out["january_minus_rest"] = round(float(np.mean(jan)) - float(np.mean(rest)), 6)
    out["why"] = ("Grinblatt-Han (JFE 2005) Table II reports the overhang "
                  "coefficient flipping sign in January. The block series "
                  "carries the month already, so the split is free — and it is "
                  "a DIAGNOSTIC: no decision rule reads it, it is not in the "
                  "family's multiplicity budget, and acting on it would need "
                  "its own registration.")
    return out


# --------------------------------------------------------------------------
# the verdict


def decide(placebo: dict, momentum: dict, primary: dict | None) -> dict:
    """TRIAL-DRAFT-C §5, applied. The falsifiers can only LOWER the standing."""
    clauses = []
    if placebo.get("placebo_pays"):
        clauses.append("the sign-flip placebo ALSO pays (§5 FAILED_VARIANT, "
                       "clause 1: it is drift, i.e. momentum again, not "
                       "disposition)")
    if momentum.get("momentum_survives"):
        clauses.append("momentum SURVIVES orthogonalisation (§5 FAILED_VARIANT, "
                       "clause 2: it was momentum in costume)")
    if clauses:
        return {"verdict": "FAILED_VARIANT", "clauses_fired": clauses,
                "reading": ("either clause alone closes the book, whatever the "
                            "primary metric did. " + "; ".join(clauses))}
    if momentum.get("momentum_survives") is None:
        return {"verdict": "CANNOT_DETERMINE", "clauses_fired": [],
                "reading": ("the placebo ran and did not fire, but the "
                            "orthogonalisation could not be computed, so the "
                            "second clause is unanswered. A check that did not "
                            "run is not a check that passed.")}
    mean = (primary or {}).get("mean_excess_net_monthly")
    t = (primary or {}).get("nw_lag2_t")
    declared = (primary or {}).get("declared_effect_size") or 0.01
    if primary is None:
        return {"verdict": "CANNOT_DETERMINE", "clauses_fired": [],
                "reading": ("both falsifiers passed, but no primary-metric "
                            "receipt was found on this checkout, so the "
                            "standing verdict cannot be restated. Run "
                            "`B_first_books_replay` first.")}
    promising = bool(mean is not None and mean >= declared
                     and t is not None and t >= T_ALIVE
                     and momentum.get("overhang_survives"))
    if promising:
        return {"verdict": "PRODUCT_PROMISING_PENDING_ERA_AND_FLOOR",
                "clauses_fired": [],
                "reading": ("both falsifiers passed AND the primary metric "
                            "clears its declared effect at t >= 2.0. §5 also "
                            "requires sign stability in 2 of 3 eras and the "
                            "$10M floor, which this job does not measure.")}
    if mean is None:
        return {"verdict": "CONDITIONAL", "clauses_fired": [],
                "reading": ("both falsifiers PASSED; the primary metric is "
                            "unreadable on this checkout, so CONDITIONAL "
                            "stands unchanged.")}
    reading = (
        f"both falsifiers PASSED, so neither §5 FAILED_VARIANT clause fires. "
        f"The standing verdict is therefore the one the primary metric earned "
        f"and no better: {mean:+.6f}/month at NW lag-2 t {t} is below the "
        f"declared {declared:.4f}/month, which is CONDITIONAL. A falsifier "
        f"that passes is not evidence FOR the book.")
    if mean <= 0:
        # TRIAL-DRAFT-C §5 Amendment 1 (2026-09-13): the same clause A §5
        # carries. v0 omitted it because its CONDITIONAL clause assumed the
        # primary had cleared; the amendment was written before the registered
        # read and records what had been seen (run 1's truncated-window read
        # and one smoke), so applying it here is applying the registration.
        clause = (f"the primary metric is on the WRONG SIDE OF ZERO: "
                  f"{mean:+.6f}/month at NW lag-2 t {t} (§5 Amendment 1, "
                  f"2026-09-13: net block-mean <= 0 over the registered slice "
                  f"closes the book whatever the falsifiers did)")
        return {"verdict": "FAILED_VARIANT", "clauses_fired": [clause],
                "primary_is_below_zero": True,
                "reading": reading + " " + clause}
    return {"verdict": "CONDITIONAL", "clauses_fired": [],
            "primary_is_below_zero": bool(mean <= 0), "reading": reading}


# --------------------------------------------------------------------------
# the replay receipt this job reads its primary metric out of


def find_replay_receipt() -> Path | None:
    """The newest non-smoke `B_first_books_replay` run receipt, or `None`.

    Delegated to the replay's own finder so that two jobs reading run 1's
    numbers can never disagree about which run they were quoting.
    """
    return find_run_receipt(smoke=False)


def primary_from_replay(path: Path | None) -> tuple[dict | None, dict | None]:
    """(Book C's `result` + declared effect, the family Holm block) from run 1."""
    import json

    if path is None or not path.is_file():
        return None, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    for b in payload.get("books") or []:
        if b.get("book") == BOOK and b.get("ran"):
            res = dict(b.get("result") or {})
            res["declared_effect_size"] = b.get("declared_effect_size")
            res["declared_mde_monthly"] = b.get("declared_mde_monthly")
            res["by_era"] = b.get("by_era")
            return res, payload.get("holm")
    return None, payload.get("holm")


# --------------------------------------------------------------------------
# the job


def C_falsifiers(*, smoke: bool = False) -> dict:                 # noqa: N802
    """The night-factory entry point. ONE receipt carrying both falsifiers."""
    start = SMOKE_START if smoke else FULL_START
    end = SMOKE_END if smoke else FULL_END
    receipt = find_replay_receipt()
    primary, family_holm = primary_from_replay(receipt)
    base = {
        "job": JOB, "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "book": BOOK, "book_id": BOOK_ID, "prereg": PREREG,
        "window": [start, end], "smoke": bool(smoke),
        "cost_curve": COST_CURVE, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "cost_caveat": ("the interim flat ruler, pending chunk 5c's TAQ curve. "
                        "Both legs of every comparison here pay it, so the "
                        "DIFFERENCES are what may be read and no LEVEL may."),
        "question": ("Does the disposition-overhang conditioner survive the two "
                     "falsifiers its own registration named before the read?"),
        "primary_metric_from_run01": primary,
        "primary_receipt": (str(receipt) if receipt else None),
        "run01_construction_defect": (
            "run 1 computed a name's overhang from 24 months of history while "
            "passing a 60-month lookback, so its first 36 overhangs per name — "
            "and the whole 1990-1994 stretch — came off a TRUNCATED "
            "reference-price window, and its pooled 395 blocks and its "
            "1990-1999 era included them although the receipt says "
            "`confirm_slice 1995-2024`. This job re-reads the SAME primary "
            "metric under the registered construction below. Run 1's number is "
            "kept on this receipt rather than replaced, because a number that "
            "quietly changes meaning is worse than two numbers a reader can "
            "difference."),
        "caveats": [
            "COST: the flat 25 bps ruler is interim (chunk 5c's TAQ curve is "
            "pending). Every leg here pays it and only DIFFERENCES are read.",
            "PRIOR, and it points the other way: Riley, Summers & Duxbury "
            "(2020, Management Science), on US data through 2016, find that "
            "momentum SURVIVES the capital-gains overhang (t 2.93) — i.e. they "
            "fail to replicate Grinblatt-Han's subsumption. Falsifier (b) "
            "firing is therefore the MODAL expectation for this book, not a "
            "surprise, and a FAILED_VARIANT on that clause is the literature's "
            "own more recent answer arriving on our tape.",
            "SCOPE: these are TRIGGERS registered in TRIAL-DRAFT-C §5. A "
            "falsifier that passes is not evidence FOR the book; it only "
            "leaves the primary metric's own verdict standing.",
        ],
        "family_multiplicity": {
            "family": FAMILY,
            "declared_family_size": 4,
            "these_legs_are_not_family_members": (
                "a falsifier is a registered TRIGGER, not a primary metric. "
                "Adding them to the family's Holm block would make the four "
                "declared tests cheaper or dearer depending on how many "
                "diagnostics a session happened to run, which is exactly what "
                "a DECLARED family size prevents."),
            "family_holm_from_run01": family_holm,
        },
        "next_test": ("the $10M-floor re-measurement of THIS book (§3 lists it "
                      "as reported-never-deciding and §5's CONDITIONAL clause "
                      "turns on it), and the v0 -> v1 event sign once L2's "
                      "typed events exist — which is a registration amendment "
                      "naming only the input, never a change to the overhang."),
    }
    panel = load_monthly_panel(start, end,
                               max_names=SMOKE_NAMES if smoke else None)
    base["months_in_panel"] = int(panel["ym"].nunique())
    base["permnos_in_panel"] = int(panel["permno"].nunique())
    try:
        inputs = book_c_inputs(panel, min_history=REGISTERED_MIN_HISTORY,
                               lookback=CGO_LOOKBACK_MONTHS)
    except BookCInputsUnavailable as exc:
        return {**base, "ran": False, "refused": str(exc),
                "headline": "C's falsifiers cannot run without the IBES panel",
                "verdict": ("REFUSED: " + str(exc))}

    want_start = SMOKE_READ_START if smoke else REGISTERED_READ_START
    read, read_start, first_cgo = registered_read_panel(panel, inputs,
                                                        read_start=want_start)
    base["registered_construction"] = {
        "cgo_min_history_months": inputs["cgo_min_history_months"],
        "cgo_lookback_months": inputs["cgo_lookback_months"],
        "cgo_window_is_full": inputs["cgo_window_is_full"],
        "registered_read_start": REGISTERED_READ_START,
        "read_start_used": read_start,
        "first_month_with_a_full_window": first_cgo,
        "months_read": int(read["ym"].nunique()) if len(read) else 0,
        "honours_the_registration": bool(not smoke
                                         and read_start == REGISTERED_READ_START),
        "why": ("TRIAL-DRAFT-C §2 freezes T = 1260 sessions (60 months at this "
                "panel's resolution) and §4 registers slice_period "
                "1995-01-01..2024-12-31, the 1995 start being a DECLARED "
                "deviation for exactly this warm-up. A smoke window cannot "
                "honour the 1995 start and says so here rather than letting a "
                "shorter read be mistaken for the registered one."),
    }
    if len(read) == 0 or read["ym"].nunique() < 4:
        return {**base, "ran": False,
                "refused": (f"the registered construction leaves "
                            f"{0 if not len(read) else read['ym'].nunique()} "
                            f"readable month(s): a 60-month window over a "
                            f"{base['months_in_panel']}-month panel starting at "
                            f"{read_start}. Widen the window or run the full pass."),
                "headline": "no month survives the registered 60-month window",
                "verdict": "REFUSED: the registered construction has no read window here"}

    primary_res = run_monthly(read, book_c_selectors(inputs)["conditioned"],
                              k=K, seed=SEED,
                              label="disposition_overhang_conditioner_v0_registered",
                              twin="unconditioned_reaction_book_v0",
                              twin_select=book_c_selectors(inputs)["unconditioned"])
    registered_primary = {
        "label": "primary_registered_construction",
        "what_it_is": ("Book C's OWN primary metric — conditioned minus "
                       "unconditioned, the same k, the same twin, the same "
                       "engine — re-read under the registered 60-month window "
                       "and the registered 1995 start. This is the registered "
                       "read, not a new test, and it is what the verdict below "
                       "is taken against."),
        "result": {k2: v for k2, v in primary_res.items()
                   if k2 not in ("blocks", "excess")},
        "by_era": by_era(primary_res),
        "declared_effect_size": 0.01, "declared_mde_monthly": 0.00724,
        "january_diagnostic": january_split(primary_res),
        "vs_run01": {
            "run01_mean_excess_net_monthly":
                (primary or {}).get("mean_excess_net_monthly"),
            "run01_nw_lag2_t": (primary or {}).get("nw_lag2_t"),
            "run01_n_blocks": (primary or {}).get("n_blocks"),
            "note": ("run 1 read a truncated-window overhang from 1990; this "
                     "reads a full-window overhang from 1995. They are not the "
                     "same measurement and neither replaces the other silently."),
        },
    }
    base["primary_registered_construction"] = registered_primary

    placebo = run_sign_flip_placebo(read, inputs)
    rows = momentum_overhang_rows(read, inputs["cgo_by_month"])
    fm = fama_macbeth_orthogonalisation(rows)
    momentum = {"falsifier": "momentum_orthogonalisation",
                "registered_as": ("TRIAL-DRAFT-C §1 quotes Grinblatt-Han: with "
                                  "overhang on the right-hand side, "
                                  "intermediate-horizon momentum DISAPPEARS. §5 "
                                  "makes its survival a FAILED_VARIANT trigger."),
                "construction": ("mom_12_1 (eleven months, skipping the most "
                                 "recent) and the book's own overhang, "
                                 "standardised in each month's cross-section, "
                                 "each regressed on the other, and the "
                                 "re-standardised residual's payoff priced "
                                 "against NEXT month's return. Both directions "
                                 "are reported."),
                "fama_macbeth": {k: v for k, v in fm.items() if k != "blocks"},
                **read_momentum_verdict(fm)}

    for_decision = dict(registered_primary["result"])
    for_decision["declared_effect_size"] = 0.01
    verdict = decide(placebo, momentum, for_decision)
    verdict["primary_read_against"] = "primary_registered_construction"
    mean = (placebo.get("vs_unconditioned") or {}).get("mean_excess_net_monthly")
    return {
        **base, "ran": True,
        "event_sign": inputs["event_sign"],
        "sign_flip_placebo": placebo,
        "momentum_orthogonalisation": momentum,
        "decision_rule": ("TRIAL-DRAFT-C §5. FAILED_VARIANT if the placebo also "
                          "pays OR momentum survives orthogonalisation — either "
                          "clause alone, whatever the primary metric did. "
                          "CONDITIONAL stands only if BOTH falsifiers pass. The "
                          "primary metric it is read against is the REGISTERED "
                          "construction's, not run 1's."),
        "headline": (
            f"registered primary "
            f"{registered_primary['result'].get('mean_excess_net_monthly')}/month "
            f"t {registered_primary['result'].get('nw_lag2_t')} over "
            f"{registered_primary['result'].get('n_blocks')} blocks (run01: "
            f"{(primary or {}).get('mean_excess_net_monthly')} over "
            f"{(primary or {}).get('n_blocks')}); placebo {mean}/month t "
            f"{(placebo.get('vs_unconditioned') or {}).get('nw_lag2_t')} "
            f"(pays: {placebo.get('placebo_pays')}); orthogonalised momentum t "
            f"{momentum.get('t_resid_mom')} vs raw {momentum.get('t_raw_mom')} "
            f"({momentum.get('verdict')})"),
        "verdict": verdict["verdict"] + " — " + verdict["reading"],
        "verdict_block": verdict,
    }


__all__ = ["C_falsifiers", "decide", "fama_macbeth_orthogonalisation",
           "find_replay_receipt", "january_split", "momentum_overhang_rows",
           "primary_from_replay", "read_momentum_verdict",
           "registered_read_panel", "run_sign_flip_placebo",
           "sign_flip_selectors"]


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    print(json.dumps(C_falsifiers(smoke=a.smoke), indent=1, default=str))
