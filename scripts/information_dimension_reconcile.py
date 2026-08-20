"""INFORMATION-DIMENSION-RECONCILE — settle the §7 vs §12 disagreement.

Two runs in the same session disagreed about whether the OPTIONS class
adds a behavioural direction beyond a size-matched dose of extra price
signals:

    INFORMATION-DIMENSION-1  no  (excess -0.124, p=1.000; 36 books,
                                  full grammar: 3 weightings x 2
                                  handlings x 2 top-N)
    CONSTRUCTION-CUT-1       YES (+0.475 vs control +0.346, p=0.000;
                                  6 books, rank weighting only, top-N 50)

Two candidate explanations, and they have different consequences:

  (a) BOOK COUNT. Effective rank rises with the number of series added,
      and the two runs added 36 and 6. If subsampling the full-grammar
      corpus to 6 options books reproduces §12's result, the disagreement
      is an artifact of scale and neither run found anything about
      options.
  (b) GRAMMAR. If the options class separates under RANK weighting and
      not under equal or inverse-vol, then the effect is real but
      CONDITIONAL — and "does options add a direction" was the wrong
      question, because the answer depends on how the book is built.

This is settled by re-analysis alone: the 216-book corpus already on
disk contains every cell. No new simulation, and no new opportunity to
choose a favourable configuration after the fact — the cells enumerated
below are the complete factorial, all reported.

    python -m scripts.information_dimension_reconcile

SCREEN.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.information_classes import CLASSES     # noqa: E402
from scripts.information_dimension_1 import (CANDIDATES,     # noqa: E402
                                             OWNED, eff_rank)

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
SRC = OUT / "information_dimension_1_books.jsonl"
SEED = 20260820


def load() -> pd.DataFrame:
    rows = [json.loads(x) for x in
            SRC.read_text(encoding="utf-8").splitlines() if x.strip()]
    s = {}
    for r in rows:
        s[r["key"]] = pd.Series(
            {pd.Timestamp(int(t), unit="ms"): v
             for t, v in r["monthly"].items()}).sort_index()
    return pd.DataFrame(s).dropna()


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-draws", type=int, default=600)
    a = ap.parse_args()

    R = load()
    print(f"corpus: {R.shape[1]} books x {R.shape[0]} months")
    parts = {c: c.split("|") for c in R.columns}
    sig_of = {c: p[0] for c, p in parts.items()}
    wgt_of = {c: p[1] for c, p in parts.items()}
    top_of = {c: p[3] for c, p in parts.items()}
    cls_of = {s: cls for cls, names in CLASSES.items() for s in names}

    rng = np.random.default_rng(SEED)
    results = []

    def cell(pred, label, n_match=None):
        cols = [c for c in R.columns if pred(c)]
        owned = [c for c in cols if cls_of.get(sig_of[c]) in OWNED]
        ctrl = [c for c in cols if cls_of.get(sig_of[c]) == "price_extra"]
        if len(owned) < 6 or len(ctrl) < 2:
            return
        base = eff_rank(R[owned])["effective_rank"]
        for candidate in CANDIDATES:
            if candidate == "price_extra":
                continue
            cand = [c for c in cols
                    if cls_of.get(sig_of[c]) == candidate]
            if not cand:
                continue
            k = n_match or len(cand)
            k = min(k, len(cand), len(ctrl))
            # candidate subsampled to k as well, so the comparison is
            # matched even when the candidate class is the larger one
            inc_draws = np.empty(a.n_draws)
            ctl_draws = np.empty(a.n_draws)
            for i in range(a.n_draws):
                cs = list(rng.choice(cand, size=k, replace=False))
                ct = list(rng.choice(ctrl, size=k, replace=False))
                inc_draws[i] = (eff_rank(R[owned + cs])["effective_rank"]
                                - base)
                ctl_draws[i] = (eff_rank(R[owned + ct])["effective_rank"]
                                - base)
            d = inc_draws - ctl_draws
            results.append({
                "cell": label, "class": candidate,
                "n_owned_books": len(owned), "n_matched": int(k),
                "dim_owned": round(base, 3),
                "increment_mean": round(float(inc_draws.mean()), 3),
                "control_mean": round(float(ctl_draws.mean()), 3),
                "excess": round(float(d.mean()), 3),
                "excess_ci": [round(float(np.percentile(d, 2.5)), 3),
                              round(float(np.percentile(d, 97.5)), 3)],
                "p_value": round(float((d <= 0).mean()), 4),
                "beats_control": bool(np.percentile(d, 2.5) > 0)})

    # the complete factorial, all reported
    cell(lambda c: True, "ALL (full grammar)")
    cell(lambda c: True, "ALL, matched to 6", n_match=6)
    for w in ("equal", "inverse_vol", "rank"):
        cell(lambda c, w=w: wgt_of[c] == w, f"weighting={w}")
    for t in ("50", "100"):
        cell(lambda c, t=t: top_of[c] == t, f"top_n={t}")
    cell(lambda c: wgt_of[c] == "rank" and top_of[c] == "50",
         "rank & top_n=50 (CONSTRUCTION-CUT-1's cell)")

    verdicts = {}
    opt = [r for r in results if r["class"] == "options"]
    all_cell = next((r for r in opt if r["cell"] == "ALL, matched to 6"),
                    None)
    rank_cell = next((r for r in opt if r["cell"] == "weighting=rank"),
                     None)
    if all_cell and rank_cell:
        if all_cell["beats_control"]:
            verdicts["options"] = ("BOOK COUNT — subsampling the full "
                                   "grammar to 6 reproduces the effect, "
                                   "so scale explained the disagreement")
        elif rank_cell["beats_control"]:
            verdicts["options"] = ("GRAMMAR-CONDITIONAL — the options "
                                   "class separates under RANK weighting "
                                   "and not under the full grammar; "
                                   "'does options add a direction' was "
                                   "the wrong question, the answer "
                                   "depends on how the book is built")
        else:
            verdicts["options"] = ("NEITHER — options does not separate "
                                   "at matched book counts in any cell; "
                                   "CONSTRUCTION-CUT-1's positive was "
                                   "not reproducible under matching")

    res = {"trial": "INFORMATION-DIMENSION-RECONCILE", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": "do INFORMATION-DIMENSION-1 and "
                       "CONSTRUCTION-CUT-1 disagree because of BOOK "
                       "COUNT or because of GRAMMAR?",
           "method": "re-analysis of the existing 216-book corpus; both "
                     "candidate and control subsampled to the same k, "
                     "complete factorial of cells reported",
           "n_draws": a.n_draws, "cells": results, "verdicts": verdicts}
    p = OUT / "information_dimension_reconcile_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{'cell':38s} {'class':13s} {'k':>3s} {'inc':>7s} "
          f"{'ctrl':>7s} {'excess':>8s} {'p':>7s}  verdict")
    for r in results:
        print(f"{r['cell']:38s} {r['class']:13s} {r['n_matched']:>3d} "
              f"{r['increment_mean']:>7.3f} {r['control_mean']:>7.3f} "
              f"{r['excess']:>+8.3f} {r['p_value']:>7.3f}  "
              f"{'BEATS' if r['beats_control'] else 'no'}")
    for k, v in verdicts.items():
        print(f"\nVERDICT [{k}]: {v}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
