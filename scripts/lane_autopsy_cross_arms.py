"""LANE-AUTOPSY CROSS-ARMS (Order 20 §5) — hermetic, reconciled, both windows.

    python -m scripts.lane_autopsy_cross_arms

WHY THIS EXISTS
===============
Two competent external reviewers read the 14-point mirror gap in OPPOSITE
directions (adjudication A6 vs B1), and the repo itself holds both signs:

  * the AUTHORITATIVE lanes (paper_nav, snapshot 2026-08-18): mirror -16.8%
    vs conviction -2.6% — the rules-managed lane 14 points BEHIND;
  * the Order 18 rules replay (lane_autopsy_1pp.json): mirror rules +14.08%
    vs conviction rules -0.91% — the equal-weight arm 15 points AHEAD.

Both cannot describe the same object. This script does what Order 20 §5
demands FIRST — reconcile the reconstruction against the authoritative NAV —
and then runs the full factorial only on what the reconciliation licenses.

Two design choices the numbers forced:

  1. HERMETIC PRICES. The Order 18 replay fetched yfinance at run time; this
     one reads `backend/data/conviction_prices.csv` (the offline loader's
     cache, delistings pinned at their cash payouts). Same input, same answer,
     every run.
  2. BOTH WINDOWS. The Order 18 replay started 2026-06-08; the authoritative
     lanes' first NAV row is 2026-06-16. Eight extra days on a book this
     volatile is a candidate explanation for the sign flip, so the factorial
     runs on both starts and prints the difference instead of arguing.

THE FACTORIAL
=============
Both lanes hold the SAME 12-name book, so Order 20's {conviction book, mirror
book} axis collapses; the real cross-arms are

    {seed-value weights, equal weights} x {never maintained, monthly}

plus the two lanes' full rule sets. The diagonal separates "EW at seed"
(a one-time bet-sizing choice) from "EW maintained" (selling relative winners
every month) — mechanically different claims that the single `weights`
mechanism flip in Order 18 could not distinguish.

DESCRIPTIVE ONLY. Nothing here seeds, flips, or writes a lane row. Where the
reconstruction disagrees with the authoritative NAV beyond tolerance, the
DISAGREEMENT is the finding and economic sentences about live lanes are
refused — the replay cells still stand as statements about the rules on these
prices.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import lane_autopsy as LA               # noqa: E402
from backend.services.conviction_prices import load_prices    # noqa: E402

OUT = REPO / "docs" / "conviction_replay" / "cross_arms_1.json"
SNAPSHOT = (REPO / "docs" / "conviction_replay"
            / "track_record_snapshot_2026-08-18.json")

#: The authoritative lanes' first recorded NAV date. The Order 18 replay's
#: 2026-06-08 start predates it by eight days (five trading days).
AUTHORITATIVE_INCEPTION = "2026-06-16"
ORDER18_START = "2026-06-08"

#: Reconstruction-vs-authoritative divergence beyond which live-lane economic
#: sentences are refused. Declared here, before the numbers are computed.
RECONCILE_TOLERANCE = 0.02

R = LA.LaneRules
CELLS: tuple[LA.LaneRules, ...] = (
    LA.CONVICTION_RULES,                                    # seed x never
    R(label="ew-at-seed-hold", optimizer="equal",
      rebalance_frequency="never",
      cost_bps_one_way=5.0, slippage_bps_one_way=1.0),      # EW x never
    R(label="seed-weights-monthly", optimizer="none",
      rebalance_frequency="monthly",
      cost_bps_one_way=5.0, slippage_bps_one_way=1.0),      # seed x monthly
    R(label="ew-monthly", optimizer="equal",
      rebalance_frequency="monthly",
      cost_bps_one_way=5.0, slippage_bps_one_way=1.0),      # EW x monthly
    LA.MIRROR_RULES,                                        # the full lane
)


def _book_shares() -> dict[str, float]:
    import yaml
    d = yaml.safe_load((REPO / "backend" / "data" / "book_lanes.yaml")
                       .read_text(encoding="utf-8"))
    return {k: float(v) for k, v in d["holdings"].items()}


def _reconcile(px: pd.DataFrame, shares: dict[str, float],
               lane_series: list[dict]) -> dict:
    """Buy-and-hold reconstruction vs the authoritative conviction NAV.

    Seeded at the authoritative inception value on the authoritative
    inception date; divergence is |recon/auth - 1| on shared dates.
    """
    auth = {r["date"]: float(r["value"]) for r in lane_series}
    d0 = min(auth)
    if pd.Timestamp(d0) not in px.index:
        return {"error": f"inception {d0} not in price index"}
    p0 = px.loc[pd.Timestamp(d0)]
    v0 = auth[d0]
    mv0 = {t: shares[t] * float(p0[t]) for t in shares}
    tot0 = sum(mv0.values())
    seeded = {t: v0 * (mv0[t] / tot0) / float(p0[t]) for t in shares}
    rows = []
    for d, a in sorted(auth.items()):
        ts = pd.Timestamp(d)
        if ts not in px.index:
            continue
        nav = sum(seeded[t] * float(px.loc[ts, t]) for t in shares)
        rows.append({"date": d, "reconstructed": round(nav, 2),
                     "authoritative": a,
                     "divergence": round(nav / a - 1.0, 6)})
    divs = [abs(r["divergence"]) for r in rows]
    worst = max(rows, key=lambda r: abs(r["divergence"])) if rows else None
    # The largest single-day JUMP in divergence marks a discrete event the
    # reconstruction does not model (a decision, a re-book, an accounting
    # change) — a steady drift would implicate the price source instead.
    jumps = [{"date": rows[i]["date"],
              "jump": round(rows[i]["divergence"] - rows[i - 1]["divergence"],
                            6)}
             for i in range(1, len(rows))]
    jumps.sort(key=lambda j: -abs(j["jump"]))
    return {"n_shared_dates": len(rows), "max_abs_divergence": max(divs),
            "mean_abs_divergence": sum(divs) / len(divs), "worst": worst,
            "largest_divergence_jumps": jumps[:3], "rows": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lane_autopsy_cross_arms")
    ap.add_argument("--end", default="")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    shares = _book_shares()
    px_all = load_prices()          # refuses if the cache is missing
    have = [t for t in shares if t in px_all.columns]
    if len(have) != len(shares):
        print(f"REFUSED: missing prices for {sorted(set(shares) - set(have))}")
        return 2
    px_all = px_all[have].ffill()
    end = a.end or str(px_all.index[-1].date())

    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    print("=" * 78)
    print("LANE-AUTOPSY CROSS-ARMS — reconcile first, then the factorial")
    print("=" * 78)

    # ── 1. reconciliation (Order 20 §5: before any economic sentence) ──────
    rec = _reconcile(px_all, shares, snap["lanes"]["conviction"])
    print(f"\n[1] conviction buy-and-hold reconstruction vs authoritative "
          f"paper_nav\n    shared dates {rec['n_shared_dates']}   "
          f"max |divergence| {rec['max_abs_divergence']:.2%}   "
          f"mean {rec['mean_abs_divergence']:.2%}")
    for j in rec["largest_divergence_jumps"]:
        print(f"    divergence JUMP {j['jump']:+.2%} on {j['date']}")
    reconciled = rec["max_abs_divergence"] <= RECONCILE_TOLERANCE
    if not reconciled:
        print(f"    -> EXCEEDS the declared {RECONCILE_TOLERANCE:.0%} "
              f"tolerance. The authoritative conviction path is NOT "
              f"buy-and-hold of the YAML seed on these prices. Live-lane "
              f"economic sentences are REFUSED below; the discrepancy is "
              f"the finding (attended: positions/decisions read under "
              f"lane-integrity-check).")

    # ── 2. the factorial, on both windows ──────────────────────────────────
    results: dict[str, list[dict]] = {}
    for start in (ORDER18_START, AUTHORITATIVE_INCEPTION):
        px = px_all.loc[pd.Timestamp(start):pd.Timestamp(end)]
        cells = []
        for rules in CELLS:
            out = LA.replay(px, shares, rules)
            out.pop("nav")
            cells.append(out)
        results[start] = cells
        print(f"\n[2] factorial, window {start} -> {end} "
              f"({len(px)} price rows)")
        print(f"    {'cell':24s} {'total':>9s} {'rebal':>6s} "
              f"{'turnover':>9s} {'cost drag':>10s}")
        for c in cells:
            print(f"    {c['label']:24s} {c['total_return']:+9.2%} "
                  f"{c['n_rebalances']:6d} {c['turnover_total']:9.3f} "
                  f"{c['cost_drag']:10.4f}")

    o18 = {c["label"]: c for c in results[ORDER18_START]}
    ain = {c["label"]: c for c in results[AUTHORITATIVE_INCEPTION]}
    shift = {lbl: ain[lbl]["total_return"] - o18[lbl]["total_return"]
             for lbl in ain}
    print("\n[3] the eight days the Order 18 window added "
          f"({ORDER18_START} vs {AUTHORITATIVE_INCEPTION} start):")
    for lbl, s in shift.items():
        print(f"    {lbl:24s} {s:+8.2%}")

    OUT.write_text(json.dumps({
        "trial": "LANE-AUTOPSY-CROSS-ARMS-1",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prices": "backend/data/conviction_prices.csv (hermetic)",
        "snapshot": SNAPSHOT.name,
        "reconcile_tolerance": RECONCILE_TOLERANCE,
        "reconciliation": {k: v for k, v in rec.items() if k != "rows"},
        "reconciliation_rows": rec["rows"],
        "reconciled": reconciled,
        "windows": results,
        "start_shift_effect": shift,
        "basis": ("RECONSTRUCTION on cached adjusted closes; paper_nav is "
                  "authoritative. Cells are statements about RULES ON THESE "
                  "PRICES; live-lane sentences require reconciled=true."),
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
