"""AEGIS-NET-PANEL-1 — materialize the canonical panel the label library waits for.

Order 20 §2.3: "canonical panel materialization + feature coverage/missingness
audit — the dataset work that needs no signature."

WHAT THIS IS
============
`net_dataset.py` is a label library with no callers: every entry point takes a
`panel` the caller must supply, and nothing in the repo supplied one. This
module is the supplier. Version 1 is deliberately narrow and honest about it:

  * PRICES: `backend/data/leakage_probe/panel.parquet` — 182 large-caps,
    2013-06 → present, adjusted closes, in-repo, hermetic. The universe is the
    TAQ calibration universe, which is the point: every name in this panel has
    a MEASURED per-name cost (`taq_cost_calibration.json`) or the declared
    band, so tournament results can be charged real costs without a join
    problem.
  * FEATURES: the `numeric_price` family only — the one family with a PIT
    store on this machine. The coverage report DECLARES the other families
    (options, expectations, event/LLM, semantic) ABSENT rather than letting
    their absence read as "no signal there": an ablation ladder needs to know
    its floor is the floor of the data, not of the world.
  * LABELS: `net_dataset.label_row` / `build_labels`, unchanged — barriers
    with days_to_barrier, magnitude, drawdown (§65-typed), realised vol,
    continuation, cross-sectional rank/decile.

PIT DISCIPLINE, ENFORCED NOT PROMISED
=====================================
Features at decision date t are computed from prices `.iloc[:t+1]`; labels
from `t+1 .. t+horizon`. `net_dataset.assert_pit_partition` — which had no
production caller until now — is called for every decision date. The test
suite additionally mutates post-t prices and asserts the features do not move.

WHAT IS COUNTED RATHER THAN DROPPED
===================================
A name absent at t (pre-IPO, dead) is excluded for a NAMED reason and
counted. A name whose forward window runs off the panel end is dropped and
counted by `build_labels` itself. An all-NaN name (PXD, MMC, SQ — the same
trio TAQ found) appears in the coverage report with its reason, never
silently missing from a table that looks complete either way.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services import net_dataset as ND

log = logging.getLogger(__name__)

PANEL = "AEGIS-NET-PANEL-1"

PRICE_SOURCE = (Path(_config.DATA_DIR) / "leakage_probe" / "panel.parquet")
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "net_panel"

#: Trading days of history a name needs before it may enter the panel — the
#: longest lookback below plus margin; also HRP's live gate, not a coincidence.
MIN_HISTORY = 252

#: Decision-date cadence. Month-end trading days: ~158 dates over the source,
#: which at ~170 active names is ~27k rows — §58's unit is the DATE, so the
#: row count is deliberately not the headline anywhere in this module.
DECISION_FREQ = "ME"

#: The feature families the tournament's ablation ladder names, with their
#: availability ON THIS MACHINE stated rather than implied.
FEATURE_FAMILIES = {
    "numeric_price": "AVAILABLE — computed here from the price panel",
    "options": "ABSENT — no PIT options store in this repo",
    "expectations": "ABSENT — no PIT estimate/revision store in this repo",
    "event_llm": "ABSENT — no PIT event/LLM feature store in this repo",
    "semantic_graph": "ABSENT — graph lives in the sibling repo, not PIT here",
}


class PanelRefused(RuntimeError):
    """A panel input is missing or unusable. Refused, never defaulted."""


def load_price_panel(path: Path | str | None = None) -> pd.DataFrame:
    p = Path(path or PRICE_SOURCE)
    if not p.exists():
        raise PanelRefused(
            f"price panel absent at {p}. Materializing an empty panel would "
            f"hand the tournament a dataset that looks like a dataset.")
    px = pd.read_parquet(p)
    if not isinstance(px.index, pd.DatetimeIndex):
        raise PanelRefused(f"{p} index is {type(px.index).__name__}, "
                           f"not DatetimeIndex")
    if not px.index.is_monotonic_increasing:
        raise PanelRefused(f"{p} index is not sorted; a shuffled calendar "
                           f"makes every 'past-only' slice a lie")
    return px


# ── the numeric_price feature family (strictly past-only per call) ─────────
def price_features(hist: pd.Series) -> dict[str, float]:
    """Features from ONE name's price history up to and including t.

    The caller guarantees `hist` ends at the decision date — nothing in here
    may look past the end of what it is handed, and the tests mutate the
    future to prove it cannot.
    """
    if len(hist) < MIN_HISTORY:
        raise PanelRefused(f"price_features needs >= {MIN_HISTORY} rows, "
                           f"got {len(hist)}")
    px = hist.to_numpy(dtype=float)
    rets = np.diff(np.log(px))
    last = px[-1]

    def mom(days: int) -> float:
        return float(last / px[-1 - days] - 1.0)

    peak252 = float(np.max(px[-252:]))
    return {
        "mom_21": mom(21),
        "mom_63": mom(63),
        "mom_252": mom(252 - 1),
        # 12-1 momentum: 12-month return skipping the most recent month —
        # the standard construction, so a literature import can be compared
        # without a silent definition change.
        "mom_12_1": float(px[-22] / px[-252] - 1.0),
        "vol_21": float(np.std(rets[-21:], ddof=1) * math.sqrt(252)),
        "vol_63": float(np.std(rets[-63:], ddof=1) * math.sqrt(252)),
        "drawdown_252": float(last / peak252 - 1.0),
    }


FEATURE_COLUMNS = ("mom_21", "mom_63", "mom_252", "mom_12_1",
                   "vol_21", "vol_63", "drawdown_252")


def decision_dates(px: pd.DataFrame) -> list[pd.Timestamp]:
    """Month-end trading days with at least MIN_HISTORY days behind them."""
    if len(px) <= MIN_HISTORY:
        raise PanelRefused(
            f"panel has {len(px)} rows; the first decision date needs "
            f"{MIN_HISTORY} behind it")
    eligible = px.index[MIN_HISTORY:]
    month_ends = pd.Series(eligible, index=eligible).groupby(
        eligible.to_period("M")).max()
    return list(month_ends)


@dataclass(frozen=True)
class MaterializeResult:
    rows: pd.DataFrame
    coverage: dict
    meta: dict


def materialize(px: pd.DataFrame, *, horizon_days: int = 20,
                barriers: tuple = ((0.20, 0.10), (0.40, 0.20), (0.75, 0.30)),
                magnitude_thresholds: tuple = (0.03, 0.05, 0.10),
                ) -> MaterializeResult:
    """The panel: one row per (decision date, active name), features + labels."""
    dates = decision_dates(px)
    all_names = list(px.columns)
    dead = [c for c in all_names if px[c].isna().all()]

    rows: list[dict] = []
    excluded: dict[str, int] = {"no_price_at_t": 0, "insufficient_history": 0}
    dropped_at_horizon = 0
    dates_used: list[str] = []
    dates_unlabelable: list[str] = []

    positions = {d: i for i, d in enumerate(px.index)}
    for d in dates:
        t = positions[d]
        if t + 1 >= len(px):
            # No forward day exists; the date cannot be labelled at any
            # horizon. Skipped here rather than letting the PIT assertion
            # fire on a clamped window that collapses onto t itself.
            continue
        # PIT partition, asserted per decision date with the exact endpoint
        # indices — the interleaved case is impossible here by construction,
        # but "impossible by construction" is what every leak said.
        ND.assert_pit_partition([t], [t + 1, min(t + horizon_days,
                                                 len(px) - 1)])
        panel_slice: dict[str, list[float]] = {}
        feats: dict[str, dict[str, float]] = {}
        for name in all_names:
            s = px[name].iloc[:t + 1]
            if pd.isna(s.iloc[-1]):
                excluded["no_price_at_t"] += 1
                continue
            s = s.dropna()
            if len(s) < MIN_HISTORY:
                excluded["insufficient_history"] += 1
                continue
            feats[name] = price_features(s)
            # Labels need the forward window too; hand build_labels the full
            # (ffilled) series and the positional index of t within it.
            full = px[name].ffill()
            panel_slice[name] = full.to_list()
        if len(panel_slice) < 2:
            continue
        try:
            built = ND.build_labels(panel_slice, t, horizon_days=horizon_days,
                                    barriers=barriers,
                                    magnitude_thresholds=magnitude_thresholds)
        except ND.LabelRefused:
            # Every name's forward window runs off the panel end — true of
            # the most recent month(s) at any horizon. Counted as a date,
            # not treated as an error and not silently absent.
            dates_unlabelable.append(str(d.date()))
            continue
        dropped_at_horizon += built["n_dropped"]
        for name, lab in built["rows"].items():
            row = {"date": d, "ticker": name, **feats[name]}
            for k, v in lab.items():
                if k.startswith("_"):
                    continue          # typed statistic objects live in code
                row[k] = v
            rows.append(row)
        if built["rows"]:
            dates_used.append(str(d.date()))

    df = pd.DataFrame(rows)
    coverage = {
        "panel": PANEL,
        "feature_families": dict(FEATURE_FAMILIES),
        "n_feature_columns_numeric_price": len(FEATURE_COLUMNS),
        "n_decision_dates": len(dates_used),
        "n_rows": len(df),
        "unit_note": "§58: the inference unit is the DATE BLOCK "
                     f"({len(dates_used)} monthly blocks), never the "
                     f"{len(df)} rows",
        "n_names_source": len(all_names),
        "dead_names": {n: "all-NaN in source (PXD delisted, SQ renamed XYZ, "
                          "MMC unexplained — same trio as TAQ)" for n in dead},
        "excluded_name_dates": excluded,
        "dropped_at_horizon_end": dropped_at_horizon,
        "dates_unlabelable_at_horizon": dates_unlabelable,
        "names_per_date": {
            "min": int(df.groupby("date")["ticker"].count().min()),
            "max": int(df.groupby("date")["ticker"].count().max()),
        } if len(df) else {},
        "date_range": [dates_used[0], dates_used[-1]] if dates_used else [],
        "missingness_in_output": float(df.isna().mean().mean())
        if len(df) else None,
    }
    meta = {
        "panel": PANEL,
        "source": str(PRICE_SOURCE),
        "source_sha256": hashlib.sha256(
            Path(PRICE_SOURCE).read_bytes()).hexdigest()
        if Path(PRICE_SOURCE).exists() else "",
        "horizon_days": horizon_days,
        "barriers": list(map(list, barriers)),
        "magnitude_thresholds": list(magnitude_thresholds),
        "min_history": MIN_HISTORY,
        "decision_freq": "month-end trading day",
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "deterministic": "same source bytes -> same rows; no RNG anywhere",
    }
    return MaterializeResult(rows=df, coverage=coverage, meta=meta)


def write(result: MaterializeResult, out_dir: Path | str | None = None,
          version: str = "v1") -> dict[str, Path]:
    d = Path(out_dir or OUT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    paths = {
        "parquet": d / f"net_panel_{version}.parquet",
        "coverage": d / f"net_panel_{version}_coverage.json",
        "meta": d / f"net_panel_{version}.meta.json",
    }
    result.rows.to_parquet(paths["parquet"], index=False)
    paths["coverage"].write_text(
        json.dumps(result.coverage, indent=2, default=str), encoding="utf-8")
    paths["meta"].write_text(
        json.dumps(result.meta, indent=2, default=str), encoding="utf-8")
    return paths
