"""GRAPH-MIDCAP-SCREEN-1 — is analyst coverage SELECTIVE further down the tape?

DECLARED BEFORE THE NUMBERS EXIST. Arms, bar and decision rule below were
written and committed before a coverage row was fetched.

WHY THIS IS CHEAP NOW, AND WAS NOT THIS MORNING
===============================================
`GRAPH-BACKBONE-2` closed the co-coverage mechanism on the live 179-name
mega-cap universe — not because the graph is dense (a degree-preserving null
predicts 95.8% density there, so density was a fact about `min_shared=1`) but
because the graph concentrates **97% as much as its own null**: n_eff 151.8 vs
156.4 ± 0.4, z = -10.6. Real, and negligible.

It also shipped the instrument that makes the successor answerable for the price
of one coverage pull: `graph_propagation.graph_beats_null()`. The finding said
to run it on a candidate universe **before a single price is fetched**. This is
that run.

The hypothesis the review left open is about SELECTIVITY: mega-caps are covered
by everyone, so co-coverage says nothing; mid and small caps are followed by a
handful of brokers, which is what the screen's own IBES graph looked like.
That is a claim about a universe, and it is now measurable rather than
arguable.

THE UNIVERSE, and why it is this one
====================================
CRSP PIT panel (`crsp_pit_monthly_v1.parquet`), eligible names in its last
month, ranked by dollar volume — the SAME eligibility and the same source the
arena's own `scan_universe` uses, so this is a liquidity BAND of an existing
universe rather than a new one invented for the occasion.

    rank    0- 180   median dollar volume  $15.8bn   <- the closed mega-cap graph
    rank  700-1600   median dollar volume  $0.5-1.1bn <- THIS SCREEN

A 15-30x drop in liquidity is the right neighbourhood for the selectivity
hypothesis, and it stays inside names that actually trade.

SAMPLED, and the sampling is declared. 900 names in the band is more yfinance
calls than this measurement is worth, so it draws **300 at a fixed seed** —
comparable to the 176 the mega-cap graph carried. Sampling lowers every firm's
degree WITHIN the sample, but `graph_beats_null` builds its null from the same
sampled graph, so the ratio is internally valid; the ratio is the statistic and
the absolute n_eff is not comparable across universes.

THE PANEL IS AS OF 2024-11-29 and it is now 2026, so some names have delisted.
They return EMPTY or STALE from the vendor and drop out. The drop rate is
reported, not hidden — a band that loses half its names is a different band.

THE DECISION RULE, DECLARED
===========================
The bar is `graph_propagation.NEFF_RATIO_BAR` = 0.80, **borrowed unchanged from
this morning** and deliberately not re-derived here, so it cannot be tuned by
whoever wants an answer.

  DISCRIMINATES (ratio <= 0.80)
      the selectivity hypothesis survives its first real test. That licenses
      DECLARING `GRAPH_PROPAGATION_MIDCAP_v2` as a full pre-registered trial
      with its own liquidity and cost assumptions — it does NOT license
      building a book, and it is not evidence of alpha.

  NEGLIGIBLE_VS_NULL (ratio > 0.80)
      the mechanism is closed on live-tradeable US equities generally rather
      than on mega-caps specifically. That is a MUCH stronger negative than
      this morning's and it retires the successor the review kept open.

Either way this is a structural measurement: no returns, no IC, no claim.

USAGE
    python -m scripts.graph_midcap_screen --fetch
    python -m scripts.graph_midcap_screen
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "backend/data/optimus/graph_propagation"
CACHE = OUT / "coverage_midcap_sample.json"
RECEIPT = OUT / "midcap_screen_receipt.json"

RANK_LO, RANK_HI = 700, 1600
SAMPLE_N = 300
SEED = 20260824
AS_OF = "2026-08-21"
N_NULL_DRAWS = 10


def band_universe() -> list[str]:
    """The declared liquidity band, from the arena's own scan source."""
    import pandas as pd

    from backend import config as _c
    from backend.services.arena.discovery import SCAN_SOURCE

    path = _c.OPTIMUS_LEDGER_DIR / "crsp_pit" / SCAN_SOURCE
    df = pd.read_parquet(path, columns=["date", "ticker", "dollar_vol",
                                        "eligible"])
    last = df["date"].max()
    r = df[(df["date"] == last) & df["eligible"].astype(bool)]
    r = r.dropna(subset=["ticker", "dollar_vol"])
    r = r.sort_values("dollar_vol", ascending=False).reset_index(drop=True)
    band = r.iloc[RANK_LO:RANK_HI]
    names = sorted({str(t).upper().replace(".", "-")
                    for t in band["ticker"] if str(t).isascii()})
    rng = np.random.default_rng(SEED)
    if len(names) > SAMPLE_N:
        idx = rng.choice(len(names), size=SAMPLE_N, replace=False)
        names = sorted(names[i] for i in idx)
    return names


def fetch() -> dict:
    from backend.services.graph_propagation import read_coverage

    names = band_universe()
    rows = {}
    for i, t in enumerate(names, 1):
        try:
            row = read_coverage(t, AS_OF)
            rows[t] = {"status": row.status, "firms": sorted(row.firms),
                       "newest": row.newest_action,
                       "stale_days": row.stale_days, "detail": row.detail[:120]}
        except Exception as e:                               # noqa: BLE001
            rows[t] = {"status": "ERROR", "firms": [],
                       "detail": f"{type(e).__name__}: {e}"[:120]}
        if i % 25 == 0:
            print(f"  {i}/{len(names)}")
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"as_of": AS_OF, "rank_band": [RANK_LO, RANK_HI],
                                 "sample_n": SAMPLE_N, "seed": SEED,
                                 "n": len(rows), "rows": rows}, indent=1),
                     encoding="utf-8")
    print(f"cached -> {CACHE}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch()

    from backend.services.graph_propagation import (NEFF_RATIO_BAR,
                                                    graph_beats_null)

    blob = json.loads(CACHE.read_text(encoding="utf-8"))
    rows = blob["rows"]
    by_status: dict[str, int] = {}
    for r in rows.values():
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    cov = {t: frozenset(r["firms"]) for t, r in rows.items()
           if r["status"] == "OK" and r["firms"]}

    print(f"attempted {len(rows)}  usable {len(cov)}  by status {by_status}")
    if len(cov) < 40:
        print("REFUSED: too few names carry coverage to measure a graph. "
              "A band that loses this many names is a different band.")
        return

    deg: dict[str, int] = {}
    for firms in cov.values():
        for f in firms:
            deg[f] = deg.get(f, 0) + 1
    firms_per_name = [len(v) for v in cov.values()]
    print(f"firm pool {len(deg)}  median firms/name "
          f"{float(np.median(firms_per_name)):.0f}")

    rep = graph_beats_null(cov, n_draws=N_NULL_DRAWS, seed=SEED)
    print()
    for k in ("n_names", "n_eff_observed", "n_eff_null_mean", "n_eff_null_sd",
              "z", "ratio_to_null", "verdict"):
        print(f"  {k:20s} {rep[k]}")

    licensed = rep["verdict"] == "DISCRIMINATES"
    print()
    print("LICENSES a GRAPH_PROPAGATION_MIDCAP_v2 pre-registration"
          if licensed else
          "CLOSES the mechanism on live-tradeable US equities generally, "
          "not just mega-caps")

    RECEIPT.write_text(json.dumps({
        "measurement_id": "GRAPH-MIDCAP-SCREEN-1",
        "licence": "PRODUCT_EXPERIMENT (structure only — no returns, no IC, "
                   "not evidence of alpha)",
        "declared_in": "scripts/graph_midcap_screen.py (this file)",
        "question": "is analyst co-coverage SELECTIVE in a mid/small-cap "
                    "liquidity band, where it is not among mega-caps?",
        "universe": {
            "source": "crsp_pit_monthly_v1.parquet, eligible, last month",
            "rank_band_by_dollar_volume": [RANK_LO, RANK_HI],
            "sample_n": SAMPLE_N, "seed": SEED,
            "attempted": len(rows), "usable": len(cov),
            "by_status": by_status,
            "firm_pool": len(deg),
            "median_firms_per_name": float(np.median(firms_per_name)),
        },
        "bar": NEFF_RATIO_BAR,
        "bar_provenance": "graph_propagation.NEFF_RATIO_BAR, declared "
                          "2026-08-24 in GRAPH-BACKBONE-2 and NOT re-derived "
                          "here",
        "megacap_comparison": {
            "n_eff_observed": 151.768, "n_eff_null_mean": 156.178,
            "ratio_to_null": 0.9718, "verdict": "NEGLIGIBLE_VS_NULL",
            "note": "absolute n_eff is not comparable across universes of "
                    "different size; the RATIO is the statistic",
        },
        "result": rep,
        "licenses_a_midcap_prereg": licensed,
    }, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}")


if __name__ == "__main__":
    main()
