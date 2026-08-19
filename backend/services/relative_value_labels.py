"""NEURAL-RELATIVE-VALUE-1 — pairwise incumbent-vs-candidate LABELS.

Order 20 §4. This module builds the labels; the model and its registration
come later, and that registration MUST confront G5 by name (the distinct
claim: the primitive unit here is relative capital substitution between two
securities — a quantity none of G5's single-name conditional shapes ever
contained).

THE DECISION BEING LABELLED
===========================
"Replace incumbent A with candidate B for the next H days." The gross label
is `fwd_B − fwd_A`; the switch is charged BOTH one-way costs (sell A, buy B)
at each name's own measured TAQ rate, or its declared band where TAQ did not
resolve it. Where the NET verdict flips inside the joint cost band, the pair
is `COST_MODEL_SENSITIVE` and EXCLUDED FROM TRAINING with the count reported
(Order 18: labelable pairs are the ones whose verdict survives the band) —
never resolved by picking an end.

THE COUNT THAT MATTERS
======================
A million pairs on 145 dates is 145 (§58; the daemon's own refusal text).
Every output of this module carries `n_date_blocks` beside `n_pairs`, and
any consumer quoting the second without the first is misquoting it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services import cost_model as CM
from backend.services import taq_calibration as TC

log = logging.getLogger(__name__)

TRIAL = "NEURAL-RELATIVE-VALUE-1"
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "relative_value"

#: Deterministic pair sampling per date — the full ordered cross of ~170
#: names is ~28k pairs/date with the information content of one date.
PAIRS_PER_DATE = 500
SEED = 20260819


class PairRefused(RuntimeError):
    """A pair label was requested from inputs that cannot honestly supply one."""


def combine_switch_cost(cost_a, cost_b):
    """The cost of selling A and buying B: both one-way legs, summed.

    Two measurements sum to a measurement. If EITHER side is a declared
    band, the joint is a band (ends summed) carrying DECLARED_CONSERVATIVE —
    the weaker provenance is the joint's provenance, because a chain's claim
    is its weakest link's.
    """
    def _ends(c):
        if isinstance(c, CM.OneWayBps):
            return c.value, c.value, c.measured
        if isinstance(c, CM.CostBand):
            return c.low.value, c.high.value, False
        raise PairRefused(
            f"expected OneWayBps or CostBand, got {type(c).__name__} — a "
            f"bare float here is the Order 18 defect verbatim")

    lo_a, hi_a, meas_a = _ends(cost_a)
    lo_b, hi_b, meas_b = _ends(cost_b)
    lo, hi = lo_a + lo_b, hi_a + hi_b
    if meas_a and meas_b:
        return CM.OneWayBps(lo, CM.MEASURED_TAQ_QUOTED,
                            basis="sum of two TAQ-measured one-way legs")
    return CM.CostBand(
        low=CM.OneWayBps(lo, CM.DECLARED_CONSERVATIVE, "joint switch band"),
        high=CM.OneWayBps(hi, CM.DECLARED_CONSERVATIVE, "joint switch band"),
        reason="at least one leg is on the declared band; the joint switch "
               "cost inherits the weaker provenance")


def pair_label(*, fwd_a: float, fwd_b: float, dd_a: float, dd_b: float,
               cost_a, cost_b) -> dict:
    """One (A→B) label: gross improvement, net verdict across the joint
    band, and the cost-free risk head."""
    for v, n in ((fwd_a, "fwd_a"), (fwd_b, "fwd_b")):
        if v is None or not np.isfinite(v):
            raise PairRefused(f"{n} is {v!r}; a pair with an invented return "
                              f"is a label about nothing")
    gross = float(fwd_b - fwd_a)
    joint = combine_switch_cost(cost_a, cost_b)
    verdict = CM.verdict_across_band(
        lambda bps: bool(gross - bps / 1e4 > 0.0), joint)
    out = {
        "improvement_gross": gross,
        "beats_net": verdict["verdict"],       # True | False | COST_MODEL_SENSITIVE
        "cost_model_sensitive": verdict["cost_model_sensitive"],
        "cost_provenance": verdict["provenance"],
        "switch_cost_evaluated_at_bps": verdict["evaluated_at_bps"],
        # Risk head is cost-free: a drawdown difference is not traded.
        "drawdown_delta": (float(dd_b - dd_a)
                           if dd_a is not None and dd_b is not None
                           and np.isfinite(dd_a) and np.isfinite(dd_b)
                           else None),
    }
    if isinstance(joint, CM.OneWayBps):
        out["improvement_net"] = gross - joint.value / 1e4
    else:
        # Never a number from a band — the net at "some" cost is the exact
        # quantity resolve_band_by_picking exists to refuse.
        out["improvement_net"] = None
    return out


def sample_pairs(names: list[str], k: int, seed: int) -> list[tuple[str, str]]:
    """Deterministic ordered pairs without self-pairs."""
    rng = np.random.default_rng(seed)
    names = sorted(names)
    n = len(names)
    if n < 2:
        raise PairRefused("a pair needs two names")
    total = n * (n - 1)
    k = min(k, total)
    flat = rng.choice(total, size=k, replace=False)
    out = []
    for f in flat:
        i, j = divmod(int(f), n - 1)
        j = j if j < i else j + 1
        out.append((names[i], names[j]))
    return out


def build_date_pairs(rows: pd.DataFrame, costs: dict, *,
                     pairs_per_date: int = PAIRS_PER_DATE,
                     seed: int = SEED) -> dict:
    """Pair labels for ONE decision date from the NET panel's per-name rows.

    `rows` must carry ticker / forward_return / forward_max_drawdown for one
    date; `costs` maps ticker → OneWayBps | CostBand (missing names refuse —
    a name without a cost object was never priced, and pricing it here at
    zero would make every switch into it free).
    """
    date = rows["date"].iloc[0]
    by_name = rows.set_index("ticker")
    date_seed = seed + int(pd.Timestamp(date).strftime("%Y%m%d"))
    pairs = sample_pairs(list(by_name.index), pairs_per_date, date_seed)
    out, sensitive, refused_cost = [], 0, 0
    for a, b in pairs:
        if a not in costs or b not in costs:
            refused_cost += 1
            continue
        lab = pair_label(
            fwd_a=by_name.at[a, "forward_return"],
            fwd_b=by_name.at[b, "forward_return"],
            dd_a=by_name.at[a, "forward_max_drawdown"],
            dd_b=by_name.at[b, "forward_max_drawdown"],
            cost_a=costs[a], cost_b=costs[b])
        if lab["cost_model_sensitive"]:
            sensitive += 1
            continue                     # counted, never trained on
        out.append({"date": date, "incumbent": a, "candidate": b, **lab})
    return {"rows": out, "n_pairs_labelled": len(out),
            "n_cost_model_sensitive": sensitive,
            "n_refused_no_cost": refused_cost,
            "n_date_blocks": 1}


def load_costs(universe: list[str]) -> dict:
    """TAQ-measured one-way per name; the declared band where TAQ refused."""
    panel = TC.load_panel()
    out = {}
    for name in universe:
        r = TC.cost_for(panel, name)
        out[name] = r.get("cost") or r.get("band")
    return out


def materialize(net_panel_path: Path | str | None = None, *,
                pairs_per_date: int = PAIRS_PER_DATE, seed: int = SEED) -> dict:
    p = Path(net_panel_path or (_config.OPTIMUS_LEDGER_DIR / "net_panel"
                                / "net_panel_v1.parquet"))
    if not p.exists():
        raise PairRefused(f"NET panel absent at {p}; pair labels derive from "
                          f"it and cannot precede it")
    panel = pd.read_parquet(p)
    costs = load_costs(sorted(panel["ticker"].unique()))
    all_rows, meta_counts = [], {"n_pairs_labelled": 0,
                                 "n_cost_model_sensitive": 0,
                                 "n_refused_no_cost": 0}
    dates = sorted(panel["date"].unique())
    for d in dates:
        res = build_date_pairs(panel[panel["date"] == d], costs,
                               pairs_per_date=pairs_per_date, seed=seed)
        all_rows.extend(res["rows"])
        for k in meta_counts:
            meta_counts[k] += res[k]
    df = pd.DataFrame(all_rows)
    meta = {
        "trial": TRIAL,
        "source": str(p),
        "pairs_per_date": pairs_per_date, "seed": seed,
        "n_date_blocks": len(dates),
        "unit_note": f"§58: {meta_counts['n_pairs_labelled']} pairs on "
                     f"{len(dates)} dates is {len(dates)} — the pair count "
                     f"is a fact about sampling, not about information",
        **meta_counts,
        "beats_net_balance": (df["beats_net"].value_counts().to_dict()
                              if len(df) else {}),
        "cost_basis": "per-name TAQ measured one-way where retired; the "
                      "declared 1-5bp band otherwise; COST_MODEL_SENSITIVE "
                      "pairs excluded from training and counted here",
        "g5_note": "the registration that evaluates any model on these "
                   "labels must confront G5 by name; the distinct claim is "
                   "pairwise capital substitution",
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
    }
    return {"rows": df, "meta": meta}


def write(result: dict, out_dir: Path | str | None = None,
          version: str = "v1") -> dict[str, Path]:
    import json
    d = Path(out_dir or OUT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    paths = {"parquet": d / f"pair_labels_{version}.parquet",
             "meta": d / f"pair_labels_{version}.meta.json"}
    result["rows"].to_parquet(paths["parquet"], index=False)
    paths["meta"].write_text(json.dumps(result["meta"], indent=2,
                                        default=str), encoding="utf-8")
    return paths
