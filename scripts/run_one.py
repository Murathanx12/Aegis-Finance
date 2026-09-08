"""ONE COMMAND FROM AN IDEA TO A GRADED, COST-AWARE, RECEIPTED RESULT.

    python -m scripts.run_one --list
    python -m scripts.run_one --arena ENGINE_BASELINE_v1
    python -m scripts.run_one --growth --cost-bps 25
    python -m scripts.run_one --reproduce            # the S1 acceptance gate

`docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` block S1. This is the missing
entry point named in `EXTERNAL_2026-09-07_FIVE_REPOS.md` section 7: freqtrade
has `freqtrade backtesting --strategy X`, Vibe-Trading has
`backtest/runner.py`, TradingAgents has `propagate(ticker, date)`, and Aegis
had a session transcript.

`--reproduce` is the acceptance gate for the whole block and is the only mode
that writes to `backend/data/optimus/strategy_interface/`. It expresses the
composite arena book and the growth-book champion through the contract and
diffs the resulting receipts against their sealed artefacts, field by field.
IT NEVER OPENS A SEALED ERA: `run_one` refuses a sealed window without an
explicit authorisation, and this script never passes one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP            # noqa: E402
from backend.strategy import (Window, arena_book_strategy,        # noqa: E402
                              compare_to_sealed, engines,
                              growth_champion_strategy, run_one)

OUT_DIR = REPO / "backend" / "data" / "optimus" / "strategy_interface"
GROWTH_DIR = REPO / "backend" / "data" / "optimus" / "growth_book"
G4_SEAL = GROWTH_DIR / "G4_seal.json"

#: The growth book's DEVELOPMENT window. The sealed era (2016-01..2024-12) is
#: deliberately absent from this file.
DEV_WINDOW = Window("2004-01", "2015-12", label="growth development", sealed=False)


def _fixture_day_state() -> dict:
    """A tiny deterministic day-state so `--arena` produces a real selection.

    Hand-built ON PURPOSE and labelled a fixture: the arena's live scan needs
    the network, and a receipt that quietly used yesterday's cache would be a
    receipt whose universe is a property of the cache directory.
    """
    names = {}
    for i in range(20):
        t = f"FIX{i:02d}"
        names[t] = {"status": "ok",
                    "close": 10.0 + i,
                    "vol63": 0.20 + 0.01 * i,
                    "ret21": 0.01 * i,
                    "streak_up": 0,
                    "scores": {"arena_composite": 1.0 - 0.05 * i}}
    return {"names": names, "fixture": True}


def run_arena(book_id: str, *, with_fixture: bool = True, verbose: bool = True) -> dict:
    s = arena_book_strategy(book_id)
    data = {"day_state": _fixture_day_state()} if with_fixture else {}
    return run_one(s, window=Window("2026-09-01", "2026-09-30", label="arena identity"),
                   data=data, argv=sys.argv, verbose=verbose)


def run_growth(*, cost_bps: float = 25.0, verbose: bool = True) -> dict:
    s = growth_champion_strategy(cost_bps=cost_bps)
    return run_one(s, window=DEV_WINDOW, argv=sys.argv, verbose=verbose)


def reproduce(*, verbose: bool = True) -> dict:
    """THE ACCEPTANCE GATE. Both books, both diffs, one receipt."""
    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out: dict = {
        "job": "S1_strategy_interface_reproduction",
        "lane": "S strategy interface",
        "licence": "PRODUCT_EXPERIMENT",
        "question": ("do the composite arena book and the growth-book champion, "
                     "expressed through `Strategy` and run through `run_one`, "
                     "reproduce their sealed artefacts?"),
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
    }

    # ------------------------------------------------ (a) composite arena book
    from backend.services.arena import spec as SPEC
    tracker.opened(SPEC.CONFIG_PATH, note="the arena book commitment")
    ar = run_arena("ENGINE_BASELINE_v1", verbose=False)
    ident = ar["engine_block"]["identity"]
    b = SPEC.load_specs()["ENGINE_BASELINE_v1"]
    sealed_identity = {"config_hash": b.config_hash,
                       "policy_fingerprint": b.policy_fingerprint,
                       "book_fingerprint": b.book_fingerprint,
                       "config_version": b.config_version}
    out["arena_composite"] = {
        "strategy_id": ar["strategy_id"],
        "strategy_fingerprint": ar["strategy_fingerprint"],
        "identity_reproduced": ident,
        "identity_sealed": sealed_identity,
        "identity_diff": compare_to_sealed(ident, sealed_identity),
        "selection": ar.get("engine_block", {}).get("selection", {}).get("chosen"),
        "sealed_backtest_receipt_exists": False,
        "why_no_backtest_diff": (
            "the arena is a FORWARD paper engine. Its sealed artefact is its "
            "IDENTITY under scheme book-v1 (config_hash, policy_fingerprint, "
            "book_fingerprint) plus the deterministic selection; its NAV rows "
            "come from live marks and there is no sealed offline replay in this "
            "repository to diff against. Reported rather than manufactured."),
    }

    # ------------------------------------------------- (b) growth champion
    growth: dict = {}
    if not G4_SEAL.exists():
        growth = {"verdict": f"CANNOT DETERMINE ({G4_SEAL} is missing)"}
    else:
        tracker.opened(G4_SEAL, note="the sealed growth receipt being reproduced")
        seal = json.loads(G4_SEAL.read_text(encoding="utf-8"))
        cells = {}
        for bps in (10.0, 25.0):
            key = f"{bps:.0f}bps"
            sealed_cell = (seal.get("development") or {}).get(key)
            if sealed_cell is None:
                cells[key] = {"verdict": f"CANNOT DETERMINE (no {key} development cell)"}
                continue
            r = run_growth(cost_bps=bps, verbose=False)
            got = dict(r["engine_block"].get("evaluate_growth") or {})
            # BYTE-FOR-BYTE, not merely value-for-value: the same serialiser
            # (`json.dumps(indent=1, default=str)`) the sealed receipt was
            # written with, so key ORDER is part of the comparison. Two dicts
            # with the same values in a different order are the same finding
            # and a different file, and the gate says byte-for-byte.
            run_bytes = json.dumps(got, indent=1, default=str)
            sealed_bytes = json.dumps(sealed_cell, indent=1, default=str)
            cells[key] = {
                "byte_identical": run_bytes == sealed_bytes,
                "sha256_run": hashlib.sha256(run_bytes.encode()).hexdigest(),
                "sha256_sealed": hashlib.sha256(sealed_bytes.encode()).hexdigest(),
                "key_order_identical": list(got) == list(sealed_cell),
                "serialiser": "json.dumps(obj, indent=1, default=str)",
                "beta_run": r["beta"],
                "beta_sealed": sealed_cell.get("beta"),
                "champion_sha256_declared": r["engine_block"].get("champion_sha256"),
                "diff": compare_to_sealed(got, sealed_cell),
                "headline_run": r["headline"],
                "headline_sealed": sealed_cell.get("headline"),
            }
        growth = {
            "strategy_id": f"growth:{seal.get('champion_genome_id')}",
            "development_cells": cells,
            "sealed_era_block": {
                "verdict": "REFUSED_BY_DESIGN",
                "why": ("the sealed era 2016-01..2024-12 is opened ONCE per frozen "
                        "champion against an append-only ledger "
                        "(SEALED_ERA_OPENINGS.jsonl), and this champion's count is "
                        "already 1. `run_one` refuses a sealed window without an "
                        "explicit authorisation and this script never passes one, "
                        "so the `sealed` block of G4_seal.json is NOT reproduced "
                        "here. That is correct behaviour, not a gap: a sealed "
                        "receipt that could be re-run on demand would not be "
                        "sealed."),
            },
        }
    out["growth_champion"] = growth

    out["wall_seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    out["generated_utc"] = datetime.now(timezone.utc).isoformat()
    ident_ok = out["arena_composite"]["identity_diff"]["identical"]
    cells_ = growth.get("development_cells") or {}
    dev_ok = (all(c.get("byte_identical") for c in cells_.values())
              if cells_ else None)
    out["headline"] = (
        f"arena identity reproduced: {ident_ok}; "
        f"growth development cells reproduced BYTE-FOR-BYTE: {dev_ok} "
        f"({len(cells_)} cost cells); "
        f"growth sealed era: REFUSED_BY_DESIGN (one opening per frozen champion)")
    RP.attach(out, sys.argv, {"job": "S1_strategy_interface_reproduction"}, tracker)
    p = OUT_DIR / "S1_reproduction.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    out["written_to"] = str(p)
    if verbose:
        print("\n" + out["headline"])
        print(f"\nreceipt: {p}")
    return out


def s2_agreement(*, verbose: bool = True) -> dict:
    """S2 GATE: does the vendored library reproduce the SEALED DSR and PBO?

    Against the growth book's own family, not a synthetic one. Two numbers are
    checked and BOTH tolerances are stated, because they are different:

    * agreement between the vendored library and `learner.inference` is checked
      at **1e-9** -- same formula, two implementations, no rounding in between;
    * agreement with the SEALED RECEIPT is checked at the receipt's own
      precision, because `learner.inference` rounds to 4 dp on the way into a
      receipt and 1e-9 against a 4-dp number would report a rounding artefact
      as a disagreement. The unrounded value is printed beside it so a reader
      can see the real delta.
    """
    import numpy as np
    import pandas as pd

    from backend.strategy import multipletesting as MT
    from backend.strategy import verdict as V
    from learner import growth_lab as GL
    from learner import inference as INF

    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = GROWTH_DIR / "G2_genome_series.parquet"
    g2p = GROWTH_DIR / "G2_generation0.json"
    out: dict = {
        "job": "S2_multipletesting_agreement",
        "lane": "S strategy interface",
        "licence": "PRODUCT_EXPERIMENT",
        "question": ("do DSR and PBO computed by the vendored Vibe-Trading "
                     "library equal the values on the sealed growth-book "
                     "receipts?"),
        "vendored_from": ("Vibe-Trading agent/src/quantlib/multipletesting.py, "
                          "MIT, HEAD a4f06a29 (2026-09-07)"),
        "tolerance_vendored_vs_learner_inference": 1e-9,
        "tolerance_vs_receipt": "the receipt's own precision (4 dp)",
        "llm_spend_usd": 0.0, "llm_calls": 0,
    }
    if not (cache.exists() and g2p.exists()):
        out["verdict"] = (f"CANNOT DETERMINE -- {cache} is gitignored and absent "
                          f"here, so the family matrix cannot be rebuilt. THE "
                          f"CHECK DID NOT RUN.")
        out["generated_utc"] = datetime.now(timezone.utc).isoformat()
        return out

    tracker.opened(g2p, note="the sealed G2 receipt whose PBO and DSR are checked")
    tracker.opened(cache, note="the family's monthly series cache")
    d = json.loads(g2p.read_text(encoding="utf-8"))
    df = pd.read_parquet(cache)
    graded = sorted(k for k, v in d["cells"].items() if v.get("beta") is not None)
    dev = {k: GL.dev(df[k].dropna()) for k in graded}
    common = None
    for k in graded:
        i = pd.Index(dev[k].index)
        common = i if common is None else common.intersection(i)
    M = np.column_stack([dev[k].reindex(common).to_numpy() for k in graded])

    # ---- PBO
    sealed_pbo = d["pbo_over_the_whole_family"]
    vend = MT.probability_of_backtest_overfitting(M, n_splits=8)
    ours = INF.pbo(M, n_splits=8)
    out["pbo"] = {
        "sealed_receipt": sealed_pbo["pbo"],
        "vendored_unrounded": float(vend.pbo),
        "learner_inference_rounded": ours["pbo"],
        "delta_vendored_vs_inference": abs(float(vend.pbo) - float(ours["pbo"])),
        "delta_vendored_vs_receipt": abs(float(vend.pbo) - float(sealed_pbo["pbo"])),
        "agrees_with_receipt_at_its_precision":
            round(float(vend.pbo), 4) == float(sealed_pbo["pbo"]),
        "n_arms": int(vend.n_strategies), "n_periods": int(vend.n_observations),
        "n_partitions": int(vend.n_splits),
        "dropped_observations": int(vend.dropped_observations),
        "verdict_match": ours["verdict"] == sealed_pbo["verdict"],
        "note": ("`learner.inference.pbo` rounds to 4 dp on the way into a "
                 "receipt; the vendored value is unrounded. The two differ only "
                 "by that rounding."),
    }

    # ---- DSR, on every leaderboard row that carries one
    panel = pd.read_parquet(
        __import__("learner.long_panel", fromlist=["LONG_TABLE"]).LONG_TABLE,
        columns=["month", "entry_date"])
    ctx = GL.market_context(panel, tracker)
    spy_dev = GL.dev(ctx["spy"].dropna())
    spy_dev.index = [str(x) for x in spy_dev.index]
    n_trials = int(json.loads((GROWTH_DIR / "DECLARATION.json")
                              .read_text(encoding="utf-8"))["family_cells_declared"])
    rows = []
    for row in d["leaderboard_by_leverage_neutral_tw"]:
        cell = row["cell"]
        if row.get("dsr") is None or cell not in dev:
            continue
        s = dev[cell]
        excess = (s - pd.Series(spy_dev).reindex(s.index)).dropna()
        m = V.moments(excess.to_numpy())
        exact = MT.deflated_sharpe_ratio(
            observed_sharpe=m["sharpe_per_observation"], n_trials=n_trials,
            n_observations=m["n"],
            trial_sharpe_std=V.analytic_trial_sharpe_std(m["n"]),
            skew=m["skew"], kurtosis=m["kurtosis_non_excess"])
        ours_dsr = INF.deflated_sharpe(excess.to_numpy(), n_trials=n_trials)
        rows.append({
            "cell": cell,
            "sealed_receipt_dsr": row["dsr"],
            "vendored_unrounded": float(exact.deflated_sharpe_ratio),
            "learner_inference_rounded": ours_dsr["dsr"],
            "delta_vendored_vs_inference": abs(float(exact.deflated_sharpe_ratio)
                                               - float(ours_dsr["dsr"])),
            "delta_vendored_vs_receipt": abs(float(exact.deflated_sharpe_ratio)
                                             - float(row["dsr"])),
            "agrees_at_receipt_precision":
                round(float(exact.deflated_sharpe_ratio), 4) == float(row["dsr"]),
        })
    n_bad = sum(1 for r in rows if not r["agrees_at_receipt_precision"])
    max_raw = max((r["delta_vendored_vs_receipt"] for r in rows), default=None)
    out["dsr"] = {
        "n_cells_checked": len(rows),
        "n_disagreements_at_receipt_precision": n_bad,
        "max_delta_vs_receipt": max_raw,
        "n_trials_declared": n_trials,
        "rows": rows,
    }
    out["wall_seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    out["generated_utc"] = datetime.now(timezone.utc).isoformat()
    out["headline"] = (
        f"PBO sealed {sealed_pbo['pbo']} vs vendored {float(vend.pbo):.16f} "
        f"(delta {out['pbo']['delta_vendored_vs_receipt']:.2e}); "
        f"DSR {len(rows)} cells checked, {n_bad} disagreements at receipt "
        f"precision, max delta {max_raw:.2e}" if rows else
        f"PBO sealed {sealed_pbo['pbo']} vs vendored {float(vend.pbo):.16f}; "
        f"DSR: no leaderboard row carries one")
    RP.attach(out, sys.argv, {"job": "S2_multipletesting_agreement"}, tracker)
    p = OUT_DIR / "S2_agreement.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    out["written_to"] = str(p)
    if verbose:
        print("\n" + out["headline"])
        print(f"\nreceipt: {p}")
    return out


def main(argv=None) -> int:                                # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="registered engines and books")
    ap.add_argument("--arena", metavar="BOOK_ID", help="run an arena book's identity+selection")
    ap.add_argument("--growth", action="store_true", help="run the growth champion (DEV window)")
    ap.add_argument("--cost-bps", type=float, default=25.0)
    ap.add_argument("--reproduce", action="store_true", help="the S1 acceptance gate")
    ap.add_argument("--s2-agreement", action="store_true",
                    help="the S2 gate: vendored DSR/PBO vs the sealed receipts")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    verbose = not a.quiet

    if a.list:
        from backend.services.arena import spec as SPEC
        print("engines:", ", ".join(engines()))
        print("arena books:", ", ".join(sorted(SPEC.load_specs())))
        return 0
    if a.reproduce:
        reproduce(verbose=verbose)
        return 0
    if a.s2_agreement:
        s2_agreement(verbose=verbose)
        return 0
    if a.arena:
        run_arena(a.arena, verbose=verbose)
        return 0
    if a.growth:
        run_growth(cost_bps=a.cost_bps, verbose=verbose)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
