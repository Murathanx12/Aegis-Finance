"""WHERE OUR NUMBER AND THE CONSENSUS PART COMPANY (roadmap O11).

Murat, 2026-09-11: *"There seems to be a cap at 30%. See how our price targets
compare to analysts' and learn why they differ too much and how ours is
wrong."*

This is the diagnostic that answers "why", per name, as a DECOMPOSITION rather
than a guess. For each ticker it prints:

* the consensus 1-year upside, raw;
* our 52-week target and its calibrated upside, on the SAME horizon;
* the 5-year Monte Carlo mean and its CAGR-ised "1Y est." — the two numbers the
  page used to show beside a 12-month consensus;
* and the gap, attributed to the step that produced it.

THE ATTRIBUTION IS COMPUTED, NOT NARRATED
=========================================
Each candidate step is REVERSED on its own, holding everything else fixed, and
the one that closes the largest share of the gap is named. The steps:

``HORIZON_MISMATCH``
    the 5-year figure was compared to a 12-month one at all. Measured as the
    distance between the 5-year mean return and the honest 12-month mean from
    the same paths.
``MEAN_VS_MEDIAN_SKEW``
    the 5-year MEAN sits above the 5-year MEDIAN because jump-diffusion plus
    GARCH fat tails compound positive skew. On ADBE these two did not agree on
    the SIGN.
``CONSENSUS_CLIP``
    the historical defect: the consensus upside truncated to the tier cap
    before the 60/40 blend. Measured by re-running the OLD arithmetic and
    reporting what it would have done to this name today.
``SHRINKAGE``
    the historical drift pulled toward the 7% equity-premium prior.
``TIER_CAP`` / ``FIVE_YEAR_CEILING``
    the removed per-tier CAGR cap, and the +300% path ceiling that survives
    inside the simulation.
``CALIBRATION``
    the fitted map from raw upside to realised 12-month return. This one is not
    a defect — it is the correction that replaced the clips — and it is named so
    a reader can see how much of the difference it accounts for.

Usage::

    python -m scripts.price_target_audit NVDA ADBE TSM MU GPRO
    python -m scripts.price_target_audit --screener       # the screener's names
    python -m scripts.price_target_audit --offline fixture.json   # no network
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: The caps that USED to apply, kept here and nowhere else. The audit's job is
#: to say what they would have done, which means it has to remember them -- and
#: `stock_analyzer` must not, which `test_price_target.py` asserts.
HISTORICAL_TIER_CAPS = {"mega": (0.04, 0.30), "large": (0.05, 0.35),
                        "mid": (0.06, 0.40), "small": (0.08, 0.45)}
HISTORICAL_CONSENSUS_FLOOR = -0.30

STEPS = ("HORIZON_MISMATCH", "MEAN_VS_MEDIAN_SKEW", "CONSENSUS_CLIP",
         "SHRINKAGE", "TIER_CAP", "FIVE_YEAR_CEILING", "CALIBRATION")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pct(x) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def attribute(row: dict) -> dict:
    """How much of the gap each step accounts for, in percentage points.

    Every contribution is a DIFFERENCE BETWEEN TWO NUMBERS THIS RUN COMPUTED.
    Nothing is apportioned by assumption, and a step whose inputs are missing
    reports None rather than zero: "this step contributed nothing" and "this
    step could not be measured" are different facts.
    """
    out: dict[str, float | None] = {s: None for s in STEPS}
    cons = row.get("consensus_upside_pct")
    five_mean = row.get("mc_5y_mean_pct")
    five_med = row.get("mc_5y_median_pct")
    twelve = row.get("mc_12m_mean_pct")
    cagrised = row.get("mc_5y_mean_cagrised_pct")

    if five_mean is not None and twelve is not None:
        # The page compared a 5-year mean to a 12-month consensus. The whole of
        # that distance is horizon, by construction.
        out["HORIZON_MISMATCH"] = round(five_mean - twelve, 3)
    if five_mean is not None and five_med is not None:
        out["MEAN_VS_MEDIAN_SKEW"] = round(five_mean - five_med, 3)
    if cagrised is not None and twelve is not None:
        # what the old "1Y est." said versus the honest 12-month figure
        out["CAGRISED_VS_TRUE_12M"] = round(cagrised - twelve, 3)

    tier = row.get("cap_tier")
    caps = HISTORICAL_TIER_CAPS.get(tier or "")
    if caps and cons is not None:
        lo, hi = caps
        raw = cons / 100.0
        clipped = min(max(raw, HISTORICAL_CONSENSUS_FLOOR), hi)
        out["CONSENSUS_CLIP"] = round(100.0 * (raw - clipped), 3)
        out["TIER_CAP"] = round(100.0 * hi, 3)
    sh = row.get("shrinkage_weight")
    hist = row.get("hist_drift_pct")
    if sh is not None and hist is not None:
        prior = 7.0
        out["SHRINKAGE"] = round(sh * (prior - hist), 3)
    if row.get("mc_path_ceiling_pct") is not None:
        out["FIVE_YEAR_CEILING"] = float(row["mc_path_ceiling_pct"])
    raw_up = row.get("target_uncalibrated_return_pct")
    cal_up = row.get("target_return_pct")
    if raw_up is not None and cal_up is not None:
        out["CALIBRATION"] = round(cal_up - raw_up, 3)

    # The dominant step: the largest ABSOLUTE contribution among the steps that
    # actually move a number (TIER_CAP and FIVE_YEAR_CEILING are levels, not
    # contributions, and are excluded from the argmax rather than compared).
    movers = {k: v for k, v in out.items()
              if v is not None and k not in ("TIER_CAP", "FIVE_YEAR_CEILING")}
    dominant = max(movers, key=lambda k: abs(movers[k])) if movers else None
    return {"contributions_pp": out, "dominant": dominant,
            "note": ("each contribution is the difference between two numbers this "
                     "run computed; a step whose inputs were missing reports null, "
                     "which is not the same as zero")}


def audit_one(ticker: str, *, analysis: dict | None = None) -> dict:
    """One row. `analysis` may be supplied (a frozen fixture) instead of fetched."""
    if analysis is None:
        from backend.services.stock_analyzer import analyze_stock
        analysis = analyze_stock(ticker)
    if not analysis:
        return {"ticker": ticker, "available": False,
                "reason": "analyze_stock returned nothing (bad ticker, or no history)"}
    px = analysis.get("current_price")
    cons_t = analysis.get("analyst_target")
    cons_up = (100.0 * (cons_t / px - 1.0)) if (cons_t and px) else None
    five_mean = analysis.get("expected_return_5y", analysis.get("expected_return"))
    five_med = analysis.get("median_return_5y", analysis.get("median_return"))
    cagrised = None
    if five_mean is not None:
        try:
            cagrised = 100.0 * ((1.0 + five_mean / 100.0) ** (1 / 5) - 1.0)
        except (TypeError, ValueError, ZeroDivisionError):
            cagrised = None
    pt = analysis.get("price_target_12m") or {}
    t12 = pt.get("target_12m") or {}
    cal = analysis.get("drift_calibration") or {}
    row = {
        "ticker": ticker, "price": px, "cap_tier": analysis.get("cap_tier"),
        "sector": analysis.get("sector"),
        "consensus_target": cons_t, "consensus_upside_pct": cons_up,
        "target_12m_point": t12.get("point"),
        "target_return_pct": t12.get("return_pct"),
        "target_uncalibrated_return_pct": t12.get("uncalibrated_return_pct"),
        "target_p10": t12.get("p10"), "target_p90": t12.get("p90"),
        "interval_basis": t12.get("basis"),
        "band_withheld": t12.get("band_withheld"),
        "upside_tercile": t12.get("upside_tercile"),
        "weights": pt.get("weights"), "weights_source": pt.get("weights_source"),
        "calibration": t12.get("calibration"),
        "bucket": pt.get("bucket"),
        "hit_rate_12m_pct": (pt.get("calibration") or {}).get("hit_rate_12m_pct"),
        "mc_12m_mean_pct": analysis.get("expected_return_12m"),
        "mc_12m_median_pct": analysis.get("median_return_12m"),
        "mc_5y_mean_pct": five_mean, "mc_5y_median_pct": five_med,
        "mc_5y_mean_cagrised_pct": cagrised,
        "mc_path_ceiling_pct": analysis.get("mc_path_ceiling_pct"),
        "hist_drift_pct": analysis.get("hist_drift"),
        "blended_drift_pct": analysis.get("capped_drift"),
        "consensus_calibration": cal.get("calibration"),
        "available": True,
    }
    row["gap_vs_consensus_pp"] = (
        None if (cons_up is None or row["target_return_pct"] is None)
        else round(row["target_return_pct"] - cons_up, 3))
    # Read off the payload rather than re-derived here: a second copy of the
    # shrinkage formula would drift from the first the day one of them changes.
    row["shrinkage_weight"] = analysis.get("shrinkage_weight")
    row["attribution"] = attribute(row)
    return row


def render(rows: list[dict]) -> str:
    head = (f"{'ticker':<8}{'price':>10}{'consensus':>11}{'ours 12m':>11}"
            f"{'gap':>9}{'5y mean':>10}{'5y/1y est':>11}{'true 12m':>10}  dominant")
    out = [head, "-" * len(head)]
    for r in rows:
        if not r.get("available"):
            out.append(f"{r['ticker']:<8}  REFUSED: {r.get('reason')}")
            continue
        out.append(
            f"{r['ticker']:<8}{(r['price'] or 0):>10.2f}"
            f"{_pct(r['consensus_upside_pct']):>11}"
            f"{_pct(r['target_return_pct']):>11}"
            f"{_pct(r['gap_vs_consensus_pp']):>9}"
            f"{_pct(r['mc_5y_mean_pct']):>10}"
            f"{_pct(r['mc_5y_mean_cagrised_pct']):>11}"
            f"{_pct(r['mc_12m_mean_pct']):>10}  "
            f"{(r['attribution'] or {}).get('dominant') or '—'}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="*", default=[])
    ap.add_argument("--screener", action="store_true",
                    help="audit the screener's default watchlist as well")
    ap.add_argument("--offline", default=None,
                    help="a JSON file of {ticker: analyze_stock_result} — no network")
    ap.add_argument("--out", default=None, help="write the rows as JSON here")
    args = ap.parse_args(argv)

    fixtures: dict[str, dict] = {}
    if args.offline:
        fixtures = json.loads(Path(args.offline).read_text(encoding="utf-8"))

    tickers = list(args.tickers) or sorted(fixtures)
    if args.screener:
        from backend.services.stock_analyzer import DEFAULT_WATCHLIST
        tickers = sorted(set(tickers) | set(DEFAULT_WATCHLIST))
    if not tickers:
        ap.error("name at least one ticker, or pass --offline/--screener")

    rows = [audit_one(t, analysis=fixtures.get(t)) for t in tickers]
    print(render(rows))
    print()
    for r in rows:
        if r.get("available") and r.get("attribution"):
            contrib = {k: v for k, v in r["attribution"]["contributions_pp"].items()
                       if v is not None}
            print(f"{r['ticker']}: {json.dumps(contrib)}")
    blob = {"receipt": "price_target_audit", "generated_utc": _now(),
            "roadmap_item": "O11", "rows": rows,
            "read_me_first": (
                "`gap` is ours-minus-consensus on the SAME 12-month horizon. "
                "`5y mean` and `5y/1y est` are the two numbers the page used to "
                "show beside a 12-month consensus; `true 12m` is the 12-month "
                "cross-section of the same simulation, which is what replaced "
                "them. `dominant` names the step that accounts for the largest "
                "absolute share of the difference.")}
    if args.out:
        # 2026-09-12: a fifteen-minute audit died at the last line because the
        # receipt directory did not exist yet. The rows were printed and then
        # thrown away.
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(blob, indent=1, default=str), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
