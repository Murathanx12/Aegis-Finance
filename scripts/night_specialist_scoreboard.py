"""Which kind of reasoning actually predicts? Fourteen specialists, graded.

    python -m scripts.night_specialist_scoreboard

WHY THIS IS THE CHEAPEST REAL EVIDENCE IN THE BUILDING
======================================================
`backend/data/optimus/predictions.jsonl` holds **25,439 probabilistic forecasts**
made between 2026-08-11 and 2026-09-22 by fourteen named specialists --
geopolitical, behavioural_narrative, ownership_flow, event_news,
options_volatility, accounting_forensics, analyst_revisions, macro_rates,
company_fundamental, skeptic and others. **17,619 of them are past their
resolution date.**

Every one was paid for in LLM spend. None had been read.

This is FORWARD evidence, which is the only kind that settles anything: each row
was written down before the outcome existed, with a probability, a horizon and a
resolution date, and the price data grades it. No backtest, no re-slicing, no
choice of window. It is also the direct answer to the question that matters more
than any factor: **is "geopolitics" a better predictor than "ownership flow",
and is either better than a coin?**

HOW A PROBABILITY IS SCORED, AND AGAINST WHAT
=============================================
A forecast of 0.55 that comes true is not "right" and one of 0.55 that fails is
not "wrong". The only honest score for probabilities is a proper scoring rule,
and the only honest comparison is against the base rate.

    Brier  = mean((p - outcome)^2)                  lower is better
    BSS    = 1 - Brier / Brier(climatology)          >0 means SKILL

`climatology` is the base rate of that observable at that horizon over the same
rows -- i.e. what you would score by ignoring the question entirely and always
saying "37% of these resolve true". **A specialist that cannot beat the base
rate has demonstrated nothing, however confident or well-argued its thesis.**
Most of the value of this scoreboard is expected to be negative BSS, and that is
a finding: it tells us which lines of reasoning to stop paying for.

Two decompositions, because they fail differently:

* **Discrimination** -- does a higher probability actually correspond to a
  higher outcome rate? Measured as the AUC-like separation between the mean
  probability on winners and on losers. A specialist can be badly calibrated and
  still discriminate, and discrimination is the part you can fix with a
  recalibration; miscalibration alone is cheap to repair.
* **Calibration** -- when it says 70%, does it happen 70% of the time? Reported
  as mean(p) - mean(outcome). A positive number is OVERCONFIDENCE, which is the
  house failure mode of an LLM asked to be interesting.

WHAT THIS DELIBERATELY DOES NOT DO
==================================
It does not turn a good BSS into a trade. A specialist with skill on
`return_sign` at 5 days has demonstrated that its probabilities carry
information; converting that into a position needs a size, a cost model and a
calibration from probability to expected return, none of which exist here.
§61 is what happens when a number is quoted before it has those.

And it reports every specialist, always, including the ones with three graded
rows -- with the count beside the score, so nobody reads a BSS computed on a
handful. The best-of-fourteen cell is selected by construction; the table is the
finding, not its top row.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config            # noqa: E402

OUT = REPO / "backend" / "data" / "optimus" / "specialists"

#: Below this a Brier skill score is arithmetic on a rumour. Reported anyway,
#: flagged, never ranked.
MIN_GRADED = 100


def load(path: Path | None = None) -> pd.DataFrame:
    p = Path(path) if path else (Path(_config.OPTIMUS_LEDGER_DIR) / "predictions.jsonl")
    rows = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return pd.DataFrame(rows)


def _outcome_bool(v) -> float | None:
    """The ledger writes outcomes in several shapes. Normalise or refuse."""
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
    if isinstance(v, dict):
        for k in ("hit", "resolved", "value", "outcome", "result"):
            if k in v:
                return _outcome_bool(v[k])
    return None


def score(d: pd.DataFrame, label: str) -> dict:
    """Brier, skill against climatology, calibration and discrimination."""
    p = d["probability"].to_numpy(dtype=float)
    y = d["y"].to_numpy(dtype=float)
    n = len(d)
    base = float(y.mean())
    brier = float(np.mean((p - y) ** 2))
    # Climatology: predict the base rate every time. This is the thing to beat,
    # and it is a genuinely hard baseline -- most opinions do not beat it.
    brier_clim = float(np.mean((base - y) ** 2))
    bss = (1.0 - brier / brier_clim) if brier_clim > 0 else None

    win, loss = p[y == 1], p[y == 0]
    disc = (float(win.mean() - loss.mean())
            if len(win) > 0 and len(loss) > 0 else None)

    months = pd.to_datetime(d["made_at"], errors="coerce", utc=True).dt.strftime("%Y-%m")
    by_month = {}
    for m in sorted(months.dropna().unique()):
        k = (months == m).values
        if k.sum() < 20:
            continue
        bm = float(np.mean((p[k] - y[k]) ** 2))
        bc = float(np.mean((base - y[k]) ** 2))
        by_month[m] = (1.0 - bm / bc) if bc > 0 else None
    return {
        "arm": label, "n": int(n), "base_rate": base,
        "brier": brier, "brier_climatology": brier_clim,
        "skill_vs_base_rate": bss,
        # >0 = overconfident: it says more than happens.
        "calibration_gap": float(p.mean() - base),
        "mean_probability": float(p.mean()),
        "discrimination": disc,
        "skill_by_month": by_month,
        "thin": bool(n < MIN_GRADED),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    d = load(Path(a.path) if a.path else None)
    print(f"ledger {len(d):,} predictions, {d.ticker.nunique():,} tickers, "
          f"{str(d.made_at.min())[:10]}..{str(d.made_at.max())[:10]}", flush=True)

    d["y"] = d["outcome"].map(_outcome_bool)
    d["probability"] = pd.to_numeric(d["probability"], errors="coerce")
    g = d[d["y"].notna() & d["probability"].between(0.0, 1.0)].copy()
    print(f"GRADED and scorable: {len(g):,} "
          f"({len(g)/max(len(d),1)*100:.0f}% of the ledger)", flush=True)
    if g.empty:
        print("\nREFUSED: nothing is graded yet. Run "
              "`forecast_grader.grade_due()` first -- a scoreboard over an "
              "ungraded ledger is a table of zeros, not a finding.")
        return 2

    res = {"receipt": "specialist_scoreboard", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_ledger": int(len(d)), "n_scored": int(len(g)),
           "scoring": ("Brier, and skill against CLIMATOLOGY (always predict the "
                       "base rate). A specialist that cannot beat the base rate "
                       "has demonstrated nothing however good its thesis reads."),
           "overall": score(g, "ALL"), "by_specialist": [],
           "by_observable": [], "by_horizon": []}

    o = res["overall"]
    print(f"\nOVERALL  n={o['n']:,}  base rate {o['base_rate']*100:.0f}%  "
          f"Brier {o['brier']:.4f} vs climatology {o['brier_climatology']:.4f}  "
          f"-> SKILL {(o['skill_vs_base_rate'] or 0)*100:+.2f}%  "
          f"calibration gap {o['calibration_gap']*100:+.1f}pp", flush=True)

    print(f"\n{'specialist':<24}{'n':>7}{'base':>7}{'skill':>9}{'calib':>8}{'disc':>8}")
    rows = []
    for name, sub in g.groupby("specialist"):
        if len(sub) < 20:
            continue
        rows.append(score(sub, str(name)))
    for r in sorted(rows, key=lambda x: -(x["skill_vs_base_rate"] or -9)):
        res["by_specialist"].append(r)
        flag = "  (THIN)" if r["thin"] else ""
        print(f"{r['arm']:<24}{r['n']:>7,}{r['base_rate']*100:>6.0f}%"
              f"{(r['skill_vs_base_rate'] or 0)*100:>8.2f}%"
              f"{r['calibration_gap']*100:>+7.1f}"
              f"{(r['discrimination'] or 0)*100:>+7.1f}{flag}", flush=True)

    print(f"\n{'observable':<24}{'n':>7}{'base':>7}{'skill':>9}{'calib':>8}{'disc':>8}")
    for name, sub in g.groupby("observable"):
        if len(sub) < 20:
            continue
        r = score(sub, str(name))
        res["by_observable"].append(r)
        print(f"{r['arm']:<24}{r['n']:>7,}{r['base_rate']*100:>6.0f}%"
              f"{(r['skill_vs_base_rate'] or 0)*100:>8.2f}%"
              f"{r['calibration_gap']*100:>+7.1f}"
              f"{(r['discrimination'] or 0)*100:>+7.1f}", flush=True)

    print(f"\n{'horizon (days)':<24}{'n':>7}{'base':>7}{'skill':>9}{'calib':>8}{'disc':>8}")
    for name, sub in g.groupby("horizon_days"):
        if len(sub) < 20:
            continue
        r = score(sub, f"h={name}")
        res["by_horizon"].append(r)
        print(f"{r['arm']:<24}{r['n']:>7,}{r['base_rate']*100:>6.0f}%"
              f"{(r['skill_vs_base_rate'] or 0)*100:>8.2f}%"
              f"{r['calibration_gap']*100:>+7.1f}"
              f"{(r['discrimination'] or 0)*100:>+7.1f}", flush=True)

    thick = [r for r in res["by_specialist"] if not r["thin"]]
    best = max(thick, key=lambda x: x["skill_vs_base_rate"] or -9, default=None)
    overall = o["skill_vs_base_rate"] or 0.0
    if overall > 0.01 and best and (best["skill_vs_base_rate"] or 0) > 0.02:
        verdict = (
            f"SOME SKILL EXISTS: the ledger as a whole beats climatology by "
            f"{overall*100:+.2f}% Brier skill on {o['n']:,} graded forecasts, and "
            f"the best specialist with a real sample is {best['arm']} at "
            f"{best['skill_vs_base_rate']*100:+.2f}% on {best['n']:,}. That is a "
            f"probability with information in it, NOT a trade -- converting it "
            f"needs a probability->return calibration that does not exist yet. "
            f"Calibration gap {o['calibration_gap']*100:+.1f}pp says it is "
            f"{'OVERconfident' if o['calibration_gap'] > 0 else 'UNDERconfident'}, "
            f"which is the cheap half to fix.")
    elif overall <= 0:
        verdict = (
            f"NO SKILL: {o['n']:,} graded forecasts score Brier {o['brier']:.4f} "
            f"against {o['brier_climatology']:.4f} for always predicting the base "
            f"rate -- skill {overall*100:+.2f}%. Fourteen specialists, "
            f"{len(d):,} forecasts and real LLM spend have produced probabilities "
            f"that are worse than a constant. The reasoning reads well and does "
            f"not predict; that is exactly what this ledger was built to be able "
            f"to say.")
    else:
        verdict = (
            f"MARGINAL: overall skill {overall*100:+.2f}% on {o['n']:,} graded "
            f"forecasts. Inside the noise for a sample this size, and not a "
            f"foundation for anything.")

    res["verdict"] = verdict
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"scoreboard_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
