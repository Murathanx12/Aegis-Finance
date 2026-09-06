"""THE GROWTH BOOK LAB — genomes, overlays, and the sealed-era latch.

`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §3. The ruler lives in
`learner/growth.py`; this module builds the things the ruler grades.

WHAT A GENOME IS
================
A `Genome` is a *recipe* and never a fitted object: an identifier, a family, a
base rule, an optional overlay, and a lineage. Two genomes with the same
`spec` produce the same monthly series to floating point, which is what makes
a mutation round (G3) auditable — the child names its parent and the diff of
the two specs IS the mutation.

THE MONTH GRID, AND WHY IT IS NOT THE CALENDAR
==============================================
The panel's book month labelled `2020-02` is the book ENTERED on 2020-02-21
and held into the −33.3% March. Grading it against calendar-February SPY would
compare two different months wearing one label — the error
`benchmark.beta_matched` used to make by `fillna(0)`-ing the risk-free leg
(BUILD_CONTINUATION_2026-09-06b). So every market leg in this module is
compounded over the book month's OWN window, `(entry_date[m], entry_date[m+1]]`,
from the pinned daily tapes:

* SPY total return — `backend/data/optimus/growth_book/spy_tr_daily_pinned.csv`,
  fetched once on 2026-09-06 and hash-pinned, so every receipt reads the same
  tape OFFLINE.
* the risk-free leg — `learner.benchmark.cash()`, the pinned Fama-French daily
  RF, also offline.

THE SEALED ERA IS LATCHED IN CODE
=================================
Development is 1999-2015 and the sealed test era is 2016-2024, opened **once
per frozen champion**. `dev()` and `sealed()` are the only two ways to slice a
series here, `sealed()` writes to an append-only openings ledger, and
`assert_development_only()` raises on any series that reaches into 2016. A
convention that lives in a docstring is a convention that gets broken at 2am;
this one raises.

THE COMMON GRADING WINDOW
=========================
The two model genomes (`lgbm_clf`, `nn_pre_causal`) exist only from 2004 —
`learner/long_panel.py` spends 1999-2003 on the five-year walk-forward warm-up
before the first test year. So the leaderboard's common development window is
**2004-01 .. 2015-12**, and the model-free genomes are additionally reported on
their own longer 1999-2015 window in a clearly separate block. Ranking books
graded on different decades against each other is exactly the failure
`evaluate_growth` refuses by aligning indexes; this constant makes the same
refusal explicit at the family level.

COSTS
=====
Panel books are netted by `evaluate.book` (turnover × 2 × bps). Exposure
overlays pay `|Δ exposure| × bps` on the RISKY leg only — moving cash between
the book and T-bills is not a round trip in SPY. Both rates, 10 and 25 bps a
side, are run for every genome; neither is a default.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "backend" / "data" / "optimus" / "growth_book"
SPY_CSV = OUT_DIR / "spy_tr_daily_pinned.csv"
SPY_META = OUT_DIR / "spy_tr_daily_pinned.json"
OPENINGS_LEDGER = OUT_DIR / "SEALED_ERA_OPENINGS.jsonl"
DECLARATION = OUT_DIR / "DECLARATION.json"

# ------------------------------------------------------------ the declaration
#: development era: search freely here.
DEV_START, DEV_END = "1999-01", "2015-12"
#: the sealed test era. Opened ONCE per frozen champion (G4).
SEALED_START, SEALED_END = "2016-01", "2024-12"
#: the window every genome — model and model-free — can be graded on. The five
#: walk-forward warm-up years of `long_panel` put the first model prediction in
#: 2004; a leaderboard mixing a 1999-start book with a 2004-start book ranks two
#: different decades.
COMMON_DEV_START = "2004-01"

COST_RATES_BPS = (10.0, 25.0)
#: the risky-leg cost an exposure overlay pays on a change of exposure.
GROSS_CAP = 2.0
FINANCING_BPS = 100.0

#: trend filter: the index's own 10-month moving average, observed AT entry.
TREND_MONTHS = 10
#: drawdown-control overlay: exposure = clip(1 - |dd3|/DD_SCALE, DD_FLOOR, 1).
DD_LOOKBACK_MONTHS = 3
DD_SCALE = 0.30
DD_FLOOR = 0.25
#: vol targeting: trailing realized vol window, and the PIT target.
VOL_DAYS = 21
VOL_BOOK_MONTHS = 6
VOL_TARGET_MIN_HISTORY = 24
VOL_EXPOSURE_CAP = 2.0

#: top-k book size for every panel genome. One value, declared, never searched.
BOOK_K = 50

_MONTHS = 12
_TRADING_DAYS = 252


# ---------------------------------------------------------------- the latch

class SealedEraViolation(RuntimeError):
    """Raised when development code reaches into 2016-2024."""


def dev(s: pd.Series, *, start: str = COMMON_DEV_START) -> pd.Series:
    """The development slice. `start` defaults to the COMMON window."""
    idx = pd.Index([str(x) for x in s.index])
    return s[(idx >= start) & (idx <= DEV_END)]


def assert_development_only(s: pd.Series, what: str = "series") -> None:
    idx = [str(x) for x in s.index]
    bad = [m for m in idx if m >= SEALED_START]
    if bad:
        raise SealedEraViolation(
            f"REFUSED: {what} carries {len(bad)} months at or after "
            f"{SEALED_START} ({bad[0]}..{bad[-1]}). The sealed era is opened "
            f"once per frozen champion, by `sealed()`, and never by a "
            f"development slice.")


def sealed_openings() -> list[dict]:
    if not OPENINGS_LEDGER.exists():
        return []
    out = []
    for line in OPENINGS_LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"MALFORMED": line[:200]})
    return out


def sealed(s: pd.Series, *, champion_id: str, champion_sha256: str,
           reason: str, ledger: Optional[Path] = None) -> pd.Series:
    """Open the sealed era. APPEND-ONLY LEDGER; the count is a receipt field.

    Every call is recorded with the champion it was opened for. `G4` asserts
    the count for its own champion is exactly 1; an accidental second call
    leaves a line behind that cannot be un-written, which is the whole point of
    an append-only record.
    """
    path = ledger or OPENINGS_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "opened_utc": datetime.now(timezone.utc).isoformat(),
        "champion_id": champion_id,
        "champion_sha256": champion_sha256,
        "reason": reason,
        "era": [SEALED_START, SEALED_END],
        "months_returned": int(sum(
            1 for m in (str(x) for x in s.index)
            if SEALED_START <= m <= SEALED_END)),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    idx = pd.Index([str(x) for x in s.index])
    return s[(idx >= SEALED_START) & (idx <= SEALED_END)]


def open_sealed_window(series: "dict[str, pd.Series]", *, champion_id: str,
                       champion_sha256: str, reason: str,
                       ledger: Optional[Path] = None) -> "dict[str, pd.Series]":
    """ONE opening of the sealed window, covering every leg of one comparison.

    An "opening" is the ACT of looking, not a call to a slicing function. The
    book, its cost-rate twin, the SPY leg and the risk-free leg are four series
    and one look, so they are one ledger line -- otherwise `sealed_era_openings`
    counts function calls and the receipt's "1" would be an artefact of how the
    comparison happened to be coded. The line records every key returned, so the
    scope of the look is on the record too.
    """
    path = ledger or OPENINGS_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    out, scope = {}, {}
    for name, s in series.items():
        idx = pd.Index([str(x) for x in s.index])
        sl = s[(idx >= SEALED_START) & (idx <= SEALED_END)]
        out[name] = sl
        scope[name] = {"months": int(len(sl)),
                       "window": [str(sl.index[0]), str(sl.index[-1])] if len(sl) else None}
    rec = {
        "opened_utc": datetime.now(timezone.utc).isoformat(),
        "champion_id": champion_id,
        "champion_sha256": champion_sha256,
        "reason": reason,
        "era": [SEALED_START, SEALED_END],
        "legs": scope,
        "note": "one look at the window; every leg of one comparison is one opening",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return out


def openings_for(champion_id: str, ledger: Optional[Path] = None) -> int:
    path = ledger or OPENINGS_LEDGER
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if json.loads(line).get("champion_id") == champion_id:
                n += 1
        except json.JSONDecodeError:
            continue
    return n


# ------------------------------------------------------------ market context

def _spy_daily(tracker=None) -> pd.Series:
    """The PINNED SPY total-return tape. Offline, hash-recorded, never fetched."""
    if not SPY_CSV.exists():
        raise SystemExit(
            f"REFUSED: {SPY_CSV} is missing. The growth book reads a PINNED SPY "
            "tape so every receipt grades the same benchmark; it does not fetch "
            "one at run time.")
    if tracker is not None:
        tracker.opened(SPY_CSV, note="pinned SPY total return, daily")
        if SPY_META.exists():
            tracker.opened(SPY_META, note="pin provenance")
    d = pd.read_csv(SPY_CSV, parse_dates=["Date"]).set_index("Date")["spy_tr"]
    return d.astype("float64").sort_index()


def _rf_daily(tracker=None) -> pd.Series:
    from learner import benchmark as BM
    bm = BM.cash()
    if tracker is not None:
        # `bm.provenance["path"]` is relative to the REPO's PARENT, so
        # `REPO / p` produced `aegis-finance/aegis-finance/backend/...` and the
        # provenance checker correctly reported INPUTS_MISSING_ON_DISK for a
        # file that HAD been opened. That is the W4b defect in miniature -- the
        # record described the open instead of naming what was opened -- so the
        # path is taken from `benchmark`'s own constant, which is the object the
        # loader actually reads.
        tracker.opened(BM._PINNED_CSV, note="pinned Fama-French daily RF")
    r = pd.Series(bm.returns).astype("float64")
    r.index = pd.to_datetime(r.index)
    return r.sort_index()


def _compound_windows(daily: pd.Series, starts: Sequence[pd.Timestamp],
                      ends: Sequence[pd.Timestamp]) -> np.ndarray:
    """prod(1+r) - 1 over each half-open window (start, end]. NaN when empty."""
    out = np.full(len(starts), np.nan)
    idx = daily.index
    v = daily.to_numpy()
    lo = np.searchsorted(idx, np.asarray(starts), side="right")
    hi = np.searchsorted(idx, np.asarray(ends), side="right")
    for i in range(len(starts)):
        if hi[i] > lo[i]:
            out[i] = float(np.prod(1.0 + v[lo[i]:hi[i]]) - 1.0)
    return out


def market_context(panel: pd.DataFrame, tracker=None) -> pd.DataFrame:
    """One row per BOOK month: the market legs over the book's own window.

    Columns, all observable at `entry_date` except `spy`/`rf` which are the
    realised return OF the month and are therefore the outcome, never an input:

      entry_date, next_entry, spy, rf,
      spy_index_at_entry     the pinned SPY TR wealth index AT entry (PIT)
      trend_ma               its `TREND_MONTHS`-month moving average AT entry
      trend_on               spy_index_at_entry >= trend_ma  (PIT)
      spy_vol_21d            annualised realised vol of SPY over the 21 trading
                             days ending AT entry (PIT)
      vol_target             expanding median of `spy_vol_21d` over months < m,
                             NaN before `VOL_TARGET_MIN_HISTORY` months (PIT)
    """
    ent = (panel[["month", "entry_date"]].dropna()
           .groupby("month", sort=True)["entry_date"].min())
    ent.index = ent.index.astype(str)
    ent = ent.sort_index()
    months = list(ent.index)
    starts = list(pd.to_datetime(ent.to_numpy()))
    # the book month ENDS when the next book is entered. The last labelled
    # month has no successor and is DROPPED rather than closed at an invented
    # date -- a month whose end we do not know is not a month we can grade.
    ends = starts[1:]
    months, starts = months[:-1], starts[:-1]

    spy_d = _spy_daily(tracker)
    rf_d = _rf_daily(tracker)
    df = pd.DataFrame(index=pd.Index(months, name="month"))
    df["entry_date"] = starts
    df["next_entry"] = ends
    df["spy"] = _compound_windows(spy_d, starts, ends)
    df["rf"] = _compound_windows(rf_d, starts, ends)

    # PIT wealth index and its moving average, both READ AT entry.
    w = (1.0 + spy_d).cumprod()
    pos = np.searchsorted(w.index, np.asarray(starts), side="right") - 1
    df["spy_index_at_entry"] = np.where(pos >= 0, w.to_numpy()[np.maximum(pos, 0)], np.nan)
    df["trend_ma"] = (df["spy_index_at_entry"]
                      .rolling(TREND_MONTHS, min_periods=TREND_MONTHS).mean())
    df["trend_on"] = (df["spy_index_at_entry"] >= df["trend_ma"])
    df.loc[df["trend_ma"].isna(), "trend_on"] = True     # warm-up: fully invested

    # trailing realised vol of SPY over the 21 trading days ENDING at entry.
    sv = spy_d.rolling(VOL_DAYS, min_periods=VOL_DAYS).std(ddof=1) * math.sqrt(_TRADING_DAYS)
    svv = sv.to_numpy()
    df["spy_vol_21d"] = np.where(pos >= 0, svv[np.maximum(pos, 0)], np.nan)
    df["vol_target"] = (df["spy_vol_21d"].shift(1)
                        .expanding(min_periods=VOL_TARGET_MIN_HISTORY).median())
    return df


# ------------------------------------------------------------------- levers

def _exposure_return(risky: pd.Series, rf: pd.Series, w: pd.Series,
                     *, cost_bps: float,
                     financing_bps: float = FINANCING_BPS) -> tuple[pd.Series, dict]:
    """Run `risky` at exposure `w`, park or borrow the rest, and pay the spread.

    `w > 1` borrows `(w-1)` at RF + `financing_bps`; `w < 1` parks `(1-w)` in
    the risk-free leg, which EARNS RF and is not free cash — the cash-drag
    error the amendment §2.3 names by its own tragedy.

    The cost is `|Δw| × cost_bps` on the risky leg only. Moving money between
    the book and T-bills is one side of a trade in the book, not two.
    """
    w = w.reindex(risky.index).astype("float64")
    r = rf.reindex(risky.index).fillna(0.0)
    spread = financing_bps / 10_000.0 / _MONTHS
    borrow = (w - 1.0).clip(lower=0.0)
    park = (1.0 - w).clip(lower=0.0)
    gross = w * risky - borrow * (r + spread) + park * r
    dw = w.diff()
    dw.iloc[0] = abs(float(w.iloc[0]))
    cost = dw.abs() * (cost_bps / 10_000.0)
    net = gross - cost
    return net, {
        "mean_exposure": round(float(w.mean()), 4),
        "max_exposure": round(float(w.max()), 4),
        "min_exposure": round(float(w.min()), 4),
        "mean_abs_exposure_change": round(float(dw.abs().mean()), 5),
        "overlay_cost_annual_pct": round(float(cost.mean()) * _MONTHS * 100.0, 4),
        "cost_convention": "|d exposure| x cost_bps on the risky leg only",
    }


def _trailing_drawdown(net: pd.Series, months: int) -> pd.Series:
    """Trailing `months`-month drawdown of the book's OWN wealth path, LAGGED.

    Lagged by one month on purpose: month m's exposure may only use information
    through m-1. An un-lagged overlay reads the month it is sizing.
    """
    w = (1.0 + net.fillna(0.0)).cumprod()
    peak = w.rolling(months, min_periods=1).max()
    dd = (w / peak - 1.0)
    return dd.shift(1).fillna(0.0)


def _trailing_vol(net: pd.Series, months: int) -> pd.Series:
    return (net.rolling(months, min_periods=months).std(ddof=1)
            * math.sqrt(_MONTHS)).shift(1)


# ------------------------------------------------------------------ genomes

@dataclass
class Genome:
    """A recipe. Never a fitted object."""
    genome_id: str
    family: str
    base: str                       # the base rule key
    spec: dict = field(default_factory=dict)
    overlay: tuple[str, ...] = ()   # ordered overlay keys
    parent_ids: tuple[str, ...] = ()
    mutation_history: tuple[str, ...] = ()
    note: str = ""

    def sha256(self) -> str:
        payload = json.dumps({
            "base": self.base, "spec": self.spec,
            "overlay": list(self.overlay)}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_json(self) -> dict:
        return {
            "genome_id": self.genome_id, "family": self.family,
            "base": self.base, "spec": dict(self.spec),
            "overlay": list(self.overlay),
            "parent_ids": list(self.parent_ids),
            "mutation_history": list(self.mutation_history),
            "note": self.note, "sha256": self.sha256(),
        }


#: overlay keys and what they mean, in the receipt's own words.
OVERLAYS = {
    "dd": (f"drawdown control: exposure = clip(1 - |trailing {DD_LOOKBACK_MONTHS}m "
           f"drawdown of the book| / {DD_SCALE}, {DD_FLOOR}, 1.0), the drawdown "
           f"lagged one month"),
    "tg": (f"trend gate: exposure 1 when the pinned SPY TR index is at or above "
           f"its {TREND_MONTHS}-month moving average AT entry, else 0 (the "
           f"proceeds earn RF)"),
    "bsc": (f"Barroso-Santa-Clara portfolio vol scaling: exposure = "
            f"target / trailing {VOL_BOOK_MONTHS}-month annualised vol of the "
            f"book, target = expanding median of that vol (PIT), capped at "
            f"{VOL_EXPOSURE_CAP}"),
}


#: the knobs a MUTATION may turn on an overlay, and the range it may turn them
#: through. A mutation outside these bounds is refused rather than clipped: a
#: proposal silently clipped to the boundary is a different proposal wearing the
#: LLM's label, and the lineage would record the one that was not run.
OVERLAY_PARAM_BOUNDS = {
    "dd_lookback_months": (1, 12),
    "dd_scale": (0.05, 0.80),
    "dd_floor": (0.0, 0.95),
    "bsc_lookback_months": (3, 24),
    "bsc_cap": (0.25, GROSS_CAP),
}


def overlay_params(spec: Optional[dict] = None) -> dict:
    """Defaults, overridden by a validated spec. REFUSES out of bounds."""
    p = {"dd_lookback_months": DD_LOOKBACK_MONTHS, "dd_scale": DD_SCALE,
         "dd_floor": DD_FLOOR, "bsc_lookback_months": VOL_BOOK_MONTHS,
         "bsc_cap": VOL_EXPOSURE_CAP}
    for k, v in (spec or {}).items():
        if k not in OVERLAY_PARAM_BOUNDS:
            continue
        lo, hi = OVERLAY_PARAM_BOUNDS[k]
        v = float(v)
        if not (lo <= v <= hi):
            raise SystemExit(
                f"REFUSED: overlay parameter {k}={v} is outside [{lo}, {hi}]. "
                "A proposal clipped to the boundary is a different proposal.")
        p[k] = int(v) if k.endswith("_months") else v
    return p


def apply_overlays(net: pd.Series, ctx: pd.DataFrame, overlay: Sequence[str],
                   *, cost_bps: float,
                   params: Optional[dict] = None) -> tuple[pd.Series, dict]:
    """Compose overlays multiplicatively on the EXPOSURE, then charge once.

    Composing on exposure rather than on returns matters: two overlays applied
    as successive `_exposure_return` calls would charge financing twice on the
    same borrowed dollar and pay the spread twice on the same trade.
    """
    if not overlay:
        return net, {"overlay": [], "note": "no overlay"}
    p = overlay_params(params)
    rf = ctx["rf"].reindex(net.index).fillna(0.0)
    w = pd.Series(1.0, index=net.index)
    detail = {}
    for key in overlay:
        if key == "dd":
            dd = _trailing_drawdown(net, int(p["dd_lookback_months"]))
            wk = (1.0 - dd.abs() / p["dd_scale"]).clip(p["dd_floor"], 1.0)
        elif key == "tg":
            wk = ctx["trend_on"].reindex(net.index).fillna(True).astype(float)
        elif key == "bsc":
            v = _trailing_vol(net, int(p["bsc_lookback_months"]))
            tgt = v.expanding(min_periods=VOL_TARGET_MIN_HISTORY).median()
            wk = (tgt / v).clip(0.0, p["bsc_cap"])
            wk = wk.fillna(1.0)
        else:
            raise SystemExit(f"REFUSED: unknown overlay {key!r}. "
                             f"Known: {sorted(OVERLAYS)}")
        detail[key] = {"description": OVERLAYS[key],
                       "mean": round(float(wk.mean()), 4),
                       "min": round(float(wk.min()), 4),
                       "max": round(float(wk.max()), 4)}
        w = w * wk
    out, meta = _exposure_return(net, rf, w, cost_bps=cost_bps)
    meta["overlay"] = list(overlay)
    meta["overlay_params"] = p
    meta["per_overlay"] = detail
    return out, meta


# ---------------------------------------------------------- base rule builds

def build_spy_base(base: str, ctx: pd.DataFrame, spec: dict,
                   *, cost_bps: float) -> tuple[pd.Series, dict]:
    """The three index genomes. Every one PIT, every one costed."""
    spy, rf = ctx["spy"].dropna(), ctx["rf"]
    if base == "spy_bh":
        # buy and hold: one entry, no rebalance. The cost is a single side,
        # charged in the first month so it is never silently zero.
        net = spy.copy()
        net.iloc[0] = float(net.iloc[0]) - cost_bps / 10_000.0
        return net, {"rule": "SPY total return, buy and hold",
                     "mean_exposure": 1.0,
                     "cost_convention": "one side at entry; no rebalance"}
    if base == "spy_trend":
        w = ctx["trend_on"].reindex(spy.index).fillna(True).astype(float)
        net, meta = _exposure_return(spy, rf, w, cost_bps=cost_bps)
        meta["rule"] = (f"SPY when its {TREND_MONTHS}-month trend is on at entry, "
                        f"else T-bills (Faber 2007)")
        return net, meta
    if base == "spy_volmgd":
        tgt, vol = ctx["vol_target"].reindex(spy.index), ctx["spy_vol_21d"].reindex(spy.index)
        w = (tgt / vol).clip(0.0, VOL_EXPOSURE_CAP).fillna(1.0)
        net, meta = _exposure_return(spy, rf, w, cost_bps=cost_bps)
        meta["rule"] = ("Moreira-Muir volatility management: exposure = "
                        "PIT-median realised vol / trailing 21-day realised vol, "
                        f"capped {VOL_EXPOSURE_CAP}")
        return net, meta
    raise SystemExit(f"REFUSED: unknown SPY base {base!r}")


def build_panel_base(base: str, panel: pd.DataFrame, spec: dict,
                     *, cost_bps: float) -> tuple[pd.Series, dict]:
    """The cross-sectional genomes: a monthly top-k book over the FLOORED panel.

    `evaluate.book` nets the measured turnover at `cost_bps` a side and returns
    the monthly net series; nothing here re-applies a cost.
    """
    from learner import evaluate as E
    pred = spec["pred_col"]
    if pred not in panel.columns:
        raise SystemExit(
            f"REFUSED: genome base {base!r} needs column {pred!r} and the panel "
            f"does not carry it. A book built on a column that is not there is a "
            f"book of NaNs that grades as zero months.")
    res = E.book(panel, pred, k=int(spec.get("k", BOOK_K)),
                 weight=spec.get("weight", "vw"), cost_bps=cost_bps,
                 ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                 hold_k=spec.get("hold_k"), return_series=True)
    if not res.get("months"):
        raise SystemExit(f"REFUSED: genome {base!r} produced no months.")
    net = res["_series"]["net"]
    net.index = pd.Index([str(x) for x in net.index], name="month")
    meta = {k: v for k, v in res.items() if k != "_series"}
    meta["rule"] = (f"monthly top-{spec.get('k', BOOK_K)} "
                    f"{spec.get('weight', 'vw')} book on {pred}")
    return net, meta


def build_blend(genomes: Sequence[tuple[pd.Series, float]]) -> pd.Series:
    """A weighted blend of already-netted books on their COMMON months.

    Blending is done on returns, not on holdings: two books that both hold a
    name pay the spread twice here and would pay it once in a merged book, so
    this is the CONSERVATIVE construction and the receipt says so.
    """
    idx = None
    for s, _ in genomes:
        i = pd.Index([str(x) for x in s.index])
        idx = i if idx is None else idx.intersection(i)
    out = pd.Series(0.0, index=idx.sort_values())
    for s, wgt in genomes:
        t = pd.Series(s.to_numpy(), index=pd.Index([str(x) for x in s.index]))
        out = out + wgt * t.reindex(out.index)
    return out


# ----------------------------------------------------- the generation-0 list

def generation_zero() -> list[Genome]:
    """Every genome family in the amendment §3, written out once.

    The list is a DECLARATION: it is hashed into `DECLARATION.json` before the
    first evaluation, so the family size the DSR deflates by is the family that
    was declared and not the family that survived.
    """
    G: list[Genome] = []

    def add(gid, family, base, spec=None, overlay=(), note=""):
        G.append(Genome(gid, family, base, spec or {}, tuple(overlay), note=note))

    # --- the index genomes
    add("spy_bh", "index", "spy_bh", note="the benchmark, run as a genome so it "
                                          "sits in the same table as its rivals")
    add("spy_trend", "index", "spy_trend",
        note="Faber 2007 / Moskowitz-Ooi-Pedersen 2012 time-series momentum")
    add("spy_volmgd", "index", "spy_volmgd", note="Moreira-Muir 2017")

    # --- the cross-sectional genomes
    add("mom_12_1", "momentum", "panel", {"pred_col": "mom_12_1", "weight": "vw"},
        note="12-1 momentum, top-50 value weighted, floored universe")
    add("mom_12_1_ew", "momentum", "panel", {"pred_col": "mom_12_1", "weight": "ew"},
        note="the equal-weight sibling: size is the difference, nothing else")
    add("mom_vol_scaled_signal", "momentum", "panel",
        {"pred_col": "mom_over_vol", "weight": "vw"},
        note="vol-scaled momentum at the SIGNAL level: mom_12_1 / vol_60d")
    add("quality_mom", "quality", "panel",
        {"pred_col": "quality_mom", "weight": "vw"},
        note="profitability x momentum: cross-sectional rank(ROE) + rank(mom_12_1)")
    add("lgbm_clf", "learner", "panel", {"pred_col": "lgbm_clf", "weight": "vw"},
        note="the incumbent classifier head, walk-forward OOS on the floored panel")
    add("nn_pre_causal", "learner", "panel",
        {"pred_col": "nn_pre_causal_seedmean", "weight": "vw"},
        note="the 8-seed causal-pretrained neural ensemble, SEED-MEAN judged")

    # --- each of the above with each overlay, and with both
    bases = list(G)
    for g in bases:
        for ov in (("dd",), ("tg",), ("dd", "tg")):
            G.append(Genome(
                genome_id=f"{g.genome_id}|{'+'.join(ov)}",
                family=g.family, base=g.base, spec=dict(g.spec), overlay=ov,
                parent_ids=(g.genome_id,),
                note=f"{g.note} + " + " + ".join(OVERLAYS[k].split(":")[0] for k in ov)))
    # --- the Barroso-Santa-Clara portfolio scaling, on the momentum families only
    for gid in ("mom_12_1", "mom_vol_scaled_signal", "lgbm_clf", "nn_pre_causal"):
        src = next(g for g in bases if g.genome_id == gid)
        G.append(Genome(f"{gid}|bsc", src.family, src.base, dict(src.spec),
                        ("bsc",), parent_ids=(gid,),
                        note="Barroso-Santa-Clara 2015 / Daniel-Moskowitz 2016 "
                             "portfolio-level vol scaling"))

    # --- 50/50 combinations: the trend-gated index with each selector
    for gid in ("mom_12_1", "quality_mom", "lgbm_clf", "nn_pre_causal"):
        G.append(Genome(f"blend50_spy_trend+{gid}", "blend", "blend",
                        {"legs": [["spy_trend", 0.5], [gid, 0.5]]},
                        parent_ids=("spy_trend", gid),
                        note="50/50 of the trend-gated index and a selector, "
                             "blended on RETURNS (each leg pays its own spread)"))
    return G


def declaration(genomes: Sequence[Genome], *, extra: Optional[dict] = None) -> dict:
    from learner import growth as GR
    d = {
        "declaration": "GROWTH BOOK — generation 0",
        "authority": "docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md §3",
        "licence": "PRODUCT_EXPERIMENT",
        "objective": GR.OBJECTIVE,
        "constraints": {
            "max_drawdown_multiple_of_spy": GR.DRAWDOWN_BUDGET_MULT,
            "cvar5_multiple_of_spy": GR.CVAR_BUDGET_MULT,
            "worst_month_floor": GR.WORST_MONTH_FLOOR,
            "gross_cap": GROSS_CAP,
            "financing_bps_over_rf": FINANCING_BPS,
        },
        "benchmark_set": [
            "SPY total return (pinned daily tape, compounded over each book "
            "month's own window)",
            "SPY total return LEVERED to the drawdown budget — the honest "
            "beta-only rival",
            "the value-weighted tradable universe (mkt_vw_1m, the panel's own "
            "market leg)",
            "the risk-free leg (pinned Fama-French daily RF)",
        ],
        "eras": {
            "development_search": [DEV_START, DEV_END],
            "development_common_grading_window": [COMMON_DEV_START, DEV_END],
            "why_common_window": (
                "learner/long_panel.py spends 1999-2003 on the five-year "
                "walk-forward warm-up, so no model genome has a prediction "
                "before 2004-01. Ranking a 1999-start book against a 2004-start "
                "book ranks two different decades."),
            "sealed_test": [SEALED_START, SEALED_END],
            "sealed_policy": "opened ONCE per frozen champion; every opening is "
                             "appended to SEALED_ERA_OPENINGS.jsonl",
        },
        "cost_rates_bps_per_side": list(COST_RATES_BPS),
        "ranking_metric": ("leverage-neutral terminal wealth — the book run at "
                           "SPY's own realised volatility with borrowed notional "
                           "charged at RF + 100 bps — with raw TW, beta and maxDD "
                           "printed beside it"),
        "overlays": dict(OVERLAYS),
        "book_k": BOOK_K,
        "generation_0_genomes": [g.to_json() for g in genomes],
        "generation_0_size": len(genomes),
        "family_size_note": (
            "the DSR deflates by every cell LOOKED AT: genomes x cost rates. "
            "That product is recorded on the summary receipt and is what "
            "n_trials is set to."),
        "declared_utc": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        d.update(extra)
    return d


def declaration_sha256(d: dict) -> str:
    """Hash of the declaration WITHOUT its own hash or timestamp.

    A hash that covers the timestamp changes on every re-read of the same
    declaration, which makes it useless as an identity.
    """
    payload = {k: v for k, v in d.items()
               if k not in ("declared_utc", "sha256", "_provenance")}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


__all__ = [
    "DEV_START", "DEV_END", "SEALED_START", "SEALED_END", "COMMON_DEV_START",
    "COST_RATES_BPS", "GROSS_CAP", "FINANCING_BPS", "BOOK_K", "OVERLAYS",
    "Genome", "SealedEraViolation",
    "dev", "sealed", "open_sealed_window", "assert_development_only",
    "sealed_openings", "openings_for",
    "market_context", "apply_overlays", "build_spy_base", "build_panel_base",
    "build_blend", "generation_zero", "declaration", "declaration_sha256",
    "overlay_params", "OVERLAY_PARAM_BOUNDS",
    "OUT_DIR", "SPY_CSV", "DECLARATION", "OPENINGS_LEDGER",
]
