"""S3-S8 -- the ported detectors, runnable, and the MMC receipt.

    python -m scripts.strategy_ports --mmc          # writes S8_mmc.json
    python -m scripts.strategy_ports --bounds       # the five live profile bounds
    python -m scripts.strategy_ports --self-test    # the planted faults, end to end

`docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` block S, rows S3-S8. The
modules themselves are wired into `run_one`, so every receipt already carries
their blocks; this script exists for the one thing a receipt cannot do, which
is measure a book's MARGINAL contribution over the ensemble it would join
across a whole panel.

$0.00 LLM spend, 0 calls, no network. Reads one local parquet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np                                              # noqa: E402
import pandas as pd                                             # noqa: E402

from backend.strategy.leak import (lookahead_analysis,          # noqa: E402
                                   recursive_analysis)
from backend.strategy.manifold import fit_manifold              # noqa: E402
from backend.strategy.numerai import mmc, per_era_scores        # noqa: E402
from backend.strategy.protections import profile_bounds         # noqa: E402

PANEL = REPO / "backend" / "data" / "optimus" / "aegis_panel" / "aegis_panel_v2.parquet"
OUT_DIR = REPO / "backend" / "data" / "optimus" / "strategy_ports"

TARGET = "ret_exc_lead1m"
#: The composite arena book AS IT ACTUALLY IS. `COMPOSITE_WEIGHTS` names six
#: signals; coverage is `{"1": 206, "6": 1}`, so 99.5% of names carry 12-1
#: momentum ONLY. The ensemble a new book would join is therefore momentum.
META = "ret_12_1"

#: (column, sign, why). The sign is the DECLARED direction of the published
#: predictor; a book that has to flip its own sign to work is a different book.
CANDIDATES = [
    ("ret_12_1", +1, "the meta-model itself -- the known answer: MMC must be 0"),
    ("be_me", +1, "book-to-market: value, the classic momentum complement"),
    ("at_gr1", -1, "asset growth (investment); low growth wins, so sign -1"),
    ("ope_be", +1, "operating profitability"),
    ("qmj", +1, "quality-minus-junk composite"),
    ("ivol_capm_252d", -1, "idiosyncratic volatility; low vol wins, so sign -1"),
]


def load_panel() -> pd.DataFrame:
    """USA, 1999-2024, above the execution floor. Every filter is named."""
    from learner.evaluate import TRADABLE_DOLLAR_VOL as FLOOR

    cols = ["eom", "excntry", "dolvol", TARGET, META] + [c for c, _, _ in CANDIDATES]
    d = pd.read_parquet(PANEL, columns=sorted(set(cols)))
    d = d[d["excntry"] == "USA"]
    d["eom"] = pd.to_datetime(d["eom"])
    d = d[(d["eom"] >= "1999-01-01") & (d["eom"] <= "2024-12-31")]
    # THE EXECUTION FLOOR, applied before believing anything about the book.
    d = d[d["dolvol"] >= FLOOR]
    d["era"] = d["eom"].dt.strftime("%Y-%m")
    d.attrs["floor"] = float(FLOOR)
    return d


def run_mmc(*, verbose: bool = True) -> dict:
    d = load_panel()
    out = {
        "receipt": "S8_mmc",
        "roadmap": "ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md block S, row S8",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "llm_calls": 0,
        "panel": {
            "source": str(PANEL.relative_to(REPO)).replace("\\", "/"),
            "filters": ["excntry == USA", "eom 1999-01..2024-12",
                        f"dolvol >= TRADABLE_DOLLAR_VOL {d.attrs['floor']:.0f}"],
            "rows": int(len(d)), "eras": int(d["era"].nunique()),
            "target": TARGET, "meta_model": META,
            "meta_model_note": (
                "the composite arena book as it actually is: COMPOSITE_WEIGHTS "
                "names six signals but coverage is {'1': 206, '6': 1}, so 99.5% "
                "of names carry 12-1 momentum only"),
        },
    }
    own = per_era_scores(d, pred_col=META, target_col=TARGET, era_col="era")
    out["meta_model_own_score"] = {k: v for k, v in own.items()
                                   if k not in ("by_era", "eras_dropped")}

    rows = {}
    for cand, sign, why in CANDIDATES:
        x = d.loc[:, ["era", TARGET, META, cand]].dropna()
        x = x.loc[:, ~x.columns.duplicated()].copy()
        x["_p"] = sign * x[cand].to_numpy(dtype=float)
        r = mmc(x, pred_col="_p", meta_col=META, target_col=TARGET, era_col="era")
        rows[cand] = {k: v for k, v in r.items()
                      if k not in ("by_era", "eras_dropped")}
        rows[cand].update({"sign": sign, "why": why, "n_rows": int(len(x))})
        if verbose:
            print(f"{cand:16s} sign{sign:+d} eras {r['n_eras']:4d} "
                  f"corr {r['mean_corr']:+.5f} MMC {r['mean_mmc']:+.5f} "
                  f"t {r['t_mmc_on_eras']} rho_meta {r['mean_corr_with_meta']:+.3f}")
    out["books"] = rows
    out["not_claimed"] = (
        "correlation space, gross, one panel, one meta-model. Not a portfolio "
        "result, not net of costs, and not evidence that a positive-MMC book "
        "makes money. A book still has to beat its benchmark after costs, at a "
        "beta, on its own receipt.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "S8_mmc.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    if verbose:
        print(f"\nreceipt: {path}")
    return out


def self_test(*, verbose: bool = True) -> dict:
    """The planted faults, run outside pytest so a reader can see them fire."""
    rng = np.random.default_rng(20260908)
    idx = pd.date_range("2020-01-01", periods=600, freq="D")
    frame = pd.DataFrame(
        {"close": 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 600)))}, index=idx)

    def build(d: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({
            "sma3": d["close"].rolling(3).mean(),
            "ewm_slow": d["close"].ewm(alpha=0.005, adjust=False).mean(),
            "tomorrow": d["close"].shift(-1) / d["close"] - 1.0,   # PLANTED LEAK
        }, index=d.index)

    la = lookahead_analysis(build, frame)
    ra = recursive_analysis(build, frame, declared_warmup=20)
    train = pd.DataFrame(rng.normal(size=(300, 3)), columns=["f1", "f2", "f3"])
    gate = fit_manifold(train)
    far = pd.DataFrame({"f1": [0.0, 50.0], "f2": [0.0, 50.0], "f3": [0.0, 50.0]})
    flags = list(int(x) for x in gate.do_predict(far))
    out = {"lookahead_biased_columns": list(la.biased_columns),
           "recursive_drifting_columns": list(ra.drifting_columns),
           "do_predict_inside_then_50sd_out": flags,
           "profile_bounds": profile_bounds()}
    if verbose:
        print(json.dumps(out, indent=1, default=str))
    return out


def main(argv=None) -> int:                                # pragma: no cover
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mmc", action="store_true", help="write the S8 MMC receipt")
    ap.add_argument("--bounds", action="store_true", help="the live profile bounds")
    ap.add_argument("--self-test", action="store_true",
                    help="run the planted faults through both leak detectors "
                         "and the manifold gate")
    a = ap.parse_args(argv)
    if a.bounds:
        print(json.dumps(profile_bounds(), indent=1))
    if a.self_test:
        self_test()
    if a.mmc:
        run_mmc()
    if not (a.mmc or a.bounds or a.self_test):
        ap.print_help()
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
