"""E_decay_sweep -- the decay-blended weights swept WITH the cost, never alone.

`Policy.decay` blends this rebalance's target with the last one
(`w_t = decay * w_{t-1} + (1 - decay) * target_t`). It exists to buy turnover
down, so the only question worth asking is whether what it buys is worth what
it costs: a blended book holds staler names, and whether the saved friction
beats the lost signal depends entirely on the cost rate. Sweeping decay at one
cost answers nothing.

So the grid is `decay x cost`, and **every decayed cell is reported beside its
own `decay = 0` twin at the SAME cost** -- the control the roadmap names, and
the same discipline `calibration.py` states for rolling-versus-all-time:
reported beside, never instead of.

WHAT THIS JOB DOES NOT DO
=========================
It does not pick a decay. It writes the table. A parameter chosen by reading
this table and then reported from the same table is the in-sample number the
farm exists to avoid producing by accident; a decay that graduates does so as
its own frozen `policy_id` through the ordinary route.

    python -m scripts.night_decay_sweep --smoke        # 2013-2016, one signal
    python -m scripts.night_decay_sweep                # the dev window
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.portfolio_farm import farm as FARM              # noqa: E402
from backend.services.portfolio_farm.panel import (PanelUnavailable,   # noqa: E402
                                                   load_panel)
from backend.services.portfolio_farm.policy import Policy              # noqa: E402

NIGHTS = REPO / "backend" / "data" / "optimus"

#: The swept lambdas. 0 is the CONTROL and is always in the grid -- a sweep
#: whose control was optional would eventually be run without it.
DECAYS = (0.0, 0.25, 0.5, 0.75)

#: The cost axis. `flat` at three rates plus the measured curve, which prices
#: each fill from the TAQ regression instead of one scalar for every name.
#: A decay that only pays for itself at 50 bps is a finding about 50 bps.
COST_CELLS = (
    {"curve": "flat", "transaction_cost_bps": 5.0, "slippage_bps": 1.0},
    {"curve": "flat", "transaction_cost_bps": 25.0, "slippage_bps": 5.0},
    {"curve": "flat", "transaction_cost_bps": 50.0, "slippage_bps": 10.0},
    {"curve": "taq_empirical"},
)

#: Signals the sweep runs. `random` is the null: a turnover control that
#: "improves" a random selector is improving the arithmetic of trading, not
#: the strategy, and that has to be visible in the same table.
SIGNALS = ("mom_12_1", "random")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cell_label(cost: dict) -> str:
    if cost.get("curve", "flat") != "flat":
        return str(cost["curve"])
    return f"flat_{cost['transaction_cost_bps']:.0f}+{cost['slippage_bps']:.0f}bps"


def build_grid(*, signals=SIGNALS, decays=DECAYS, costs=COST_CELLS,
               holding_days: int = 21, top_k: int = 12,
               universe_n: int = 500) -> list[Policy]:
    """Every (signal, cost, decay) cell. The control lambda is never dropped."""
    out: list[Policy] = []
    for sig in signals:
        for cost in costs:
            for lam in decays:
                out.append(Policy(signal=sig, holding_days=holding_days,
                                  top_k=top_k, universe_n=universe_n,
                                  decay=float(lam), **cost))
    return out


def table_rows(results) -> list[dict]:
    """One row per policy, with its `decay=0` twin's numbers alongside.

    The twin is found by POLICY FIELDS, not by position: a run that reordered
    its results would otherwise pair a cell with somebody else's control, and
    the pairing is the entire content of this table.
    """
    by_key = {}
    for r in results:
        p = r.policy
        by_key[(p.signal, _cell_label({"curve": p.curve,
                                       "transaction_cost_bps": p.transaction_cost_bps,
                                       "slippage_bps": p.slippage_bps}),
                p.decay)] = r
    rows = []
    for (sig, cell, lam), r in sorted(by_key.items()):
        m, d = r.metrics or {}, r.diagnostics or {}
        ctrl = by_key.get((sig, cell, 0.0))
        cm = (ctrl.metrics or {}) if ctrl is not None else {}
        rows.append({
            "signal": sig, "cost_cell": cell, "decay": lam,
            "policy_id": r.policy.policy_id, "label": r.policy.label,
            "status": m.get("status"),
            "terminal_usd": m.get("terminal_usd"),
            "cagr_pct": m.get("cagr_pct"),
            "sharpe": m.get("sharpe"),
            "max_drawdown_pct": m.get("max_drawdown_pct"),
            "turnover_annual": m.get("turnover_annual"),
            "total_cost_usd": m.get("total_cost_usd"),
            "mean_realised_cost_bps": d.get("mean_realised_cost_bps"),
            "n_decisions": d.get("n_decisions"),
            # the control, on the SAME row, so no reader has to join two tables
            "control_decay0_terminal_usd": cm.get("terminal_usd"),
            "control_decay0_cagr_pct": cm.get("cagr_pct"),
            "control_decay0_turnover_annual": cm.get("turnover_annual"),
            "control_decay0_total_cost_usd": cm.get("total_cost_usd"),
            "vs_control_cagr_pp": (
                None if (m.get("cagr_pct") is None or cm.get("cagr_pct") is None)
                else round(m["cagr_pct"] - cm["cagr_pct"], 3)),
            "vs_control_turnover_ratio": (
                None if not cm.get("turnover_annual")
                else round((m.get("turnover_annual") or 0.0)
                           / cm["turnover_annual"], 4)),
        })
    return rows


def E_decay_sweep(smoke: bool = False, run: int = 1, *,
                  start: int | None = None, end: int | None = None,
                  out_dir: Path | None = None) -> dict:
    t0 = time.perf_counter()
    start = int(start or (2013 if smoke else 1999))
    end = int(end or (2016 if smoke else 2015))
    signals = ("mom_12_1",) if smoke else SIGNALS
    try:
        panel = load_panel(start, end, reduce_for_universe_n=500)
    except PanelUnavailable as exc:
        return {"job": "E_decay_sweep", "licence": "PRODUCT_EXPERIMENT",
                "llm_spend_usd": 0.0, "available": False,
                "headline": f"PANEL UNAVAILABLE: {exc}",
                "verdict": ("CANNOT DETERMINE: the CRSP window this sweep "
                            "declares is not on this checkout. A sweep over a "
                            "silently shortened window would report a CAGR "
                            "over a period nobody declared."),
                "written_utc": _now()}
    policies = build_grid(signals=signals)
    results = FARM.run_many(panel, policies, progress=False)
    rows = table_rows(results)

    # THE CAVEAT THAT HAS TO TRAVEL WITH THE TABLE. On a window where the
    # underlying signal LOSES money, trading less of it is better for a reason
    # that has nothing to do with friction: the blend simply dilutes exposure
    # to a bad selector. A reader who sees "+7 pp at lambda 0.75" without
    # seeing that the control returned -12.8%/yr would take the wrong lesson,
    # so the count of losing controls is computed and stated rather than left
    # to be noticed.
    losing = sorted({r["cost_cell"] for r in rows
                     if r["decay"] == 0.0 and (r["cagr_pct"] or 0.0) < 0})
    real = [r for r in rows if r["signal"] != "random" and r["decay"] > 0]
    cheaper = [r for r in real if (r["vs_control_turnover_ratio"] or 9) < 1.0]
    better = [r for r in real if (r["vs_control_cagr_pp"] or -9) > 0]
    head = (f"{len(rows)} cells ({len(signals)} signals x {len(COST_CELLS)} "
            f"cost regimes x {len(DECAYS)} lambdas) over {start}-{end}; "
            f"{len(cheaper)}/{len(real)} decayed cells trade less than their "
            f"own lambda=0 twin, {len(better)}/{len(real)} also beat it on net "
            f"CAGR")
    return {
        "job": "E_decay_sweep", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "available": True,
        "question": ("Does blending this rebalance's target with the last one "
                     "buy more in saved friction than it costs in staleness, "
                     "and at which cost rate?"),
        "window": f"{start}-{end}", "smoke": bool(smoke),
        "grid": {"decays": list(DECAYS),
                 "cost_cells": [_cell_label(c) for c in COST_CELLS],
                 "signals": list(signals),
                 "control": "decay=0.0 at the SAME cost cell, on every row"},
        "n_policies": len(policies), "n_results": len(results),
        "rows": rows,
        "cost_cells_whose_control_LOSES_money": losing,
        "caveat": (
            "In a cost cell whose lambda=0 control has a NEGATIVE CAGR, a "
            "decayed cell's advantage is partly dilution of a losing selector "
            "and not saved friction alone. Read `vs_control_cagr_pp` beside "
            "`control_decay0_cagr_pct`, never on its own."
            if losing else
            "Every lambda=0 control in this grid has a non-negative CAGR, so "
            "the decayed cells are not being flattered by dilution of a "
            "losing selector."),
        "seconds": round(time.perf_counter() - t0, 1),
        "headline": head,
        "verdict": ("DESCRIPTIVE TABLE, NO SELECTION: this job writes the "
                    "decay x cost grid beside its own controls and picks "
                    "nothing. A lambda chosen by reading this table and then "
                    "reported from it would be an in-sample number."),
        "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    payload = E_decay_sweep(smoke=a.smoke, run=a.run, start=a.start, end=a.end)
    dest = (Path(a.out) if a.out else
            NIGHTS / f"night_factory_{datetime.now(timezone.utc):%Y-%m-%d}"
            / f"E_decay_sweep_run{a.run:02d}{'_smoke' if a.smoke else ''}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"E_decay_sweep: {payload['headline']}\n  -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
