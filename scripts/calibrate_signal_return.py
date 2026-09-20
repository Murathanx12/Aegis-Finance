"""C7_signal_calibration — the map from a signal's DECILE to a RETURN MAGNITUDE.

    python -m scripts.night_factory_jobs C7_signal_calibration
    python -m scripts.night_factory_jobs C7_signal_calibration --smoke

Roadmap `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§15.2 chunk 22, from Murat's review of 2026-09-20
(`docs/research_notes/2026-09-20/feedback_murat_review_2026-09-20_evening.md`
issue 1), and his words are the whole specification:

    "The ROI engine is not yet an ROI engine. Expected return comes from the
    leading signal FAMILY's average; downside from the ticker's vol. So among
    names sharing a family the rule prefers the lowest-vol name. Useful, but a
    different problem. Needed: calibrate signal strength into return magnitude
    — an out-of-sample map from signal decile to expected abnormal return and
    downside at 5/21/63/126 sessions, with uncertainty around each estimate.
    Then each company gets its own mu_i rather than inheriting the same average
    return from the signal family."

WHAT THIS JOB PRODUCES, AND WHAT IT REFUSES TO PRODUCE
======================================================
One JSON per signal under `backend/data/optimus/calibration/`, read back by
`backend/services/signal_calibration.py` and consumed by `roi_rank` as the
per-name `mu_i`. Each file carries, per horizon, one row per decile:

    mean abnormal return · 20th-percentile abnormal return (the DOWNSIDE) ·
    sd · n_names · n_date_blocks · a block-bootstrap CI on the mean

plus the D_hi − D_lo spread with a Newey-West t, gross AND net of the declared
cost ruler, the two nulls, and a Holm-adjusted p over the family of every
(signal x horizon) this job computed.

**The family is DERIVED, never listed.** `leadable_signals()` reads
`recommendation._ADAPTERS` and asks the registry which of them it permits as a
PICKER. A signal the registry does not license to lead is not calibrated here
at all and is named with the grade/role that excluded it — calibrating a FILTER
into a return would license it to pick, which is the exact substitution
`recommendation.py` exists to stop.

**A leadable signal with no point-in-time panel on disk is `NO_PANEL`, named,
never guessed.** The refusal states which table is missing, by path.

THE CONSTRUCTION, PRINTED BECAUSE IT IS A TEST INPUT
====================================================
(`feedback_the_registered_construction_is_a_test_input.md`: Book C warmed its
overhang at 24 months against a registered 60 and the number moved by 40%.)

* **Anchors** are the LAST SESSION OF EACH MONTH on the CRSP daily tape. A
  score is read at that close; the forward return starts the NEXT session.
* **Forward return** at horizon h = the name's own compounded return over the
  h sessions after the anchor. A name whose block ends before `anchor + h`
  contributes nothing to that cell and is COUNTED: the CRSP daily file carries
  no delisting return, so this drops the worst outcomes and the direction of
  that bias is stated on every receipt rather than implied.
* **Abnormal** = that return minus the EQUAL-WEIGHT mean of the same signal's
  own scored universe at the same anchor and horizon. Not the market: the
  question is which DECILE of this signal's universe did better, and an
  equal-weight universe mean is the benchmark that makes the decile means sum
  to zero and the spread invariant to it.
* **Universe** is the signal's OWN licensed cap band (`in_universe`,
  `config.SIGNAL_UNIVERSE_BANDS`), applied with the live thresholds
  (`SIGNAL_UNIVERSE_SMALL_MAX_USD` / `..._MID_MAX_USD`) on the CRSP cap at the
  anchor session. Those thresholds are nominal dollars of 2026 applied to 2006
  — an anachronism the live engine also commits, so the calibration commits it
  identically rather than measuring a universe the engine cannot reproduce.
* **Walk-forward**: expanding window, DECILE CUT POINTS REFIT EVERY YEAR on all
  rows strictly before the test year; first test year = the panel's first year
  + `CALIB_FIRST_TEST_YEAR_OFFSET`. Every statistic in the table is computed on
  test rows only. Ties go DOWN (`side="left"`), so a tied block lands in one
  decile instead of being split by a cut point that cannot separate it.
* **Costs**: the implied turnover of a MONTHLY-REBALANCED decile portfolio.
  One-way turnover tau costs `2 x tau x CALIB_COST_BPS_PER_SIDE` per month
  (the replaced slice is sold and bought), scaled to the horizon by h/21.
  Gross and net are BOTH printed; the verdict reads the net.
* **Blocks**: the dependence unit is the MONTH (CANON §58). `n_date_blocks` is
  a count of months, never of rows, and the bootstrap resamples months.

THE TWO NULLS
=============
1. **The shuffled panel, end to end.** Scores are permuted WITHIN each anchor
   date, and the whole pipeline is rerun on the shuffled panel — cut points
   refit on the shuffled training window, decile table rebuilt, spread and NW t
   recomputed. This is the review's "(a) shuffled scores within date" and
   "(b) the map fit on the shuffled panel" as one operation, because they are
   one operation, and saying otherwise would be dressing one test as two.
2. **The shuffled DISTRIBUTION.** The same within-date shuffle repeated
   `CALIB_NULL_DRAWS` times on the out-of-sample panel, giving an empirical
   distribution of the spread and of the decile monotonicity. The real value is
   reported as a percentile of it. A spread inside the shuffled distribution is
   not a spread, whatever its t.

THE VERDICT, AND WHAT EACH ONE LICENSES DOWNSTREAM
==================================================
Taken at `CALIB_DECIDING_HORIZON_SESSIONS` (21 sessions ~ one month, the unit
every row of `config.SIGNAL_MEASURED_RETURN` is already quoted in):

* ``CALIBRATED`` — net spread > 0, Holm-adjusted p < `CALIB_HOLM_ALPHA`, AND
  the decile map is monotone. Only this licenses EXPLOIT: `roi_rank` takes the
  candidate's OWN decile's mean as `mu_i` and its p20 as the downside, and
  `decision_authority` admits to EXPLOIT only a name whose leading signal
  carries this verdict. EXPLOIT can therefore become non-empty only through
  measurement.
* ``WEAK`` — net > 0 but not significant, or monotonicity could not be
  determined. Feeds EXPLORE's posterior (mean and se from the decile CI).
  Murat, rule 36: uncertain means INVESTIGATE, never freeze.
* ``INVERTED`` — net spread < 0 at Holm p < alpha. A hypothesis killed for
  EXPLOIT: the map runs the wrong way and no amount of Kelly fixes that.
* ``NO_PANEL`` — refused by name, with the table that is missing.
* ``REFUSED`` — a panel exists and the test could not run (too few month
  blocks, no usable decile cell). Named, never silently absent.

LICENCE: PRODUCT_EXPERIMENT. No order path, no promotion, no research claim.
This job reads only local parquet on disk: no network, no model, no LLM.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config                                    # noqa: E402
from backend.strategy.verdict import holm                     # noqa: E402

#: Never a literal. Unset means TODAY; `NIGHT_RUN_DATE` reproduces a past night.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")

WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
SEC_INSIDER = (REPO / "backend" / "data" / "optimus" / "sec_insider"
               / "insider_events_v1.parquet")
JKP_LATE = WRDS / "jkp_global_factor_usa.parquet"
JKP_FULL = WRDS / "jkp_full"

CALIBRATED = "CALIBRATED"
WEAK = "WEAK"
INVERTED = "INVERTED"
NO_PANEL = "NO_PANEL"
REFUSED = "REFUSED"
VERDICTS: tuple[str, ...] = (CALIBRATED, WEAK, INVERTED, NO_PANEL, REFUSED)

#: The file schema `signal_calibration.py` validates against.
SCHEMA = "aegis.signal_calibration.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def output_dir(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else REPO
    return base / config.CALIB_OUTPUT_DIR


def output_path(signal_id: str, *, run_date: Optional[str] = None,
                root: Optional[Path] = None, smoke: bool = False) -> Path:
    """The file this run writes for one signal.

    A SMOKE run writes `<signal>_<date>_smoke.json`, and
    `signal_calibration.latest_for` ignores any name carrying `_smoke`. A
    three-year smoke panel that overwrote the real map would size positions on
    a window the job itself refused to grade.
    """
    tail = "_smoke" if smoke else ""
    return output_dir(root) / f"{signal_id}_{run_date or RUN_DATE}{tail}.json"


# ===========================================================================
# THE FAMILY — derived from the adapters and the registry, never listed
# ===========================================================================


def leadable_signals(registry: Any = None) -> tuple[list[str], dict[str, str]]:
    """(the signals `score_candidates` can LEAD with, why each other cannot).

    Derived: `recommendation._ADAPTERS` is what reads data, and
    `registry.permits(id, "PICKER")` is what licenses an adapter to order
    names. A guard derives its inputs or refuses; a hard-coded list here would
    silently stop matching the engine the first time the registry moved.
    """
    from backend.services import signal_registry as R
    from backend.services.recommendation import _ADAPTERS

    reg = registry if registry is not None else R.load()
    lead: list[str] = []
    excluded: dict[str, str] = {}
    for ad in _ADAPTERS:
        sid = ad.signal_id
        try:
            sig = reg.get(sid)
        except Exception as exc:  # noqa: BLE001 - the reason IS the result
            excluded[sid] = (f"the registry could not answer for it "
                             f"({type(exc).__name__}: {exc}), so it is not "
                             f"treated as leadable")
            continue
        if reg.permits(sid, "PICKER"):
            lead.append(sid)
        else:
            excluded[sid] = (
                f"registry grades it {sig.evidence_grade}/{sig.permitted_role} "
                f"— it is read and printed and may never LEAD a ranking, so "
                f"calibrating a return for it would license a "
                f"{sig.permitted_role.lower()} to pick")
    return lead, excluded


def licensed_bands(signal_id: str, registry: Any = None) -> tuple[set, str]:
    """The cap bands this signal is licensed in, and the universe string."""
    from backend.services import signal_registry as R

    reg = registry if registry is not None else R.load()
    sig = reg.get(signal_id)
    uni = (sig.universe or "").strip()
    return set(config.SIGNAL_UNIVERSE_BANDS.get(uni) or set()), uni


def _band_of(cap_usd: np.ndarray) -> np.ndarray:
    """The live `recommendation.cap_band` rule, vectorised."""
    out = np.full(len(cap_usd), "unknown", dtype=object)
    ok = np.isfinite(cap_usd) & (cap_usd > 0)
    out[ok & (cap_usd <= config.SIGNAL_UNIVERSE_SMALL_MAX_USD)] = "small"
    out[ok & (cap_usd > config.SIGNAL_UNIVERSE_SMALL_MAX_USD)
        & (cap_usd <= config.SIGNAL_UNIVERSE_MID_MAX_USD)] = "mid"
    out[ok & (cap_usd > config.SIGNAL_UNIVERSE_MID_MAX_USD)] = "large"
    return out


# ===========================================================================
# THE TAPE AND THE ANCHOR UNIVERSE
# ===========================================================================


def build_universe(*, start_year: int, end_year: int,
                   smoke: bool = False) -> tuple[Any, pd.DataFrame, dict]:
    """(tape, one row per (permno, month-end anchor), the construction block).

    `load_daily` and `Tape` are imported from `night_factory_jobs` rather than
    re-implemented: a second session index in this repo would be a second thing
    to get wrong, and every book already priced on that tape would stop being
    comparable to this one.
    """
    from scripts.night_factory_jobs import Tape, load_daily

    years = list(range(int(start_year), int(end_year) + 1))
    present = [y for y in years if (WRDS / f"crsp_dsf_{y}.parquet").exists()]
    if not present:
        raise FileNotFoundError(
            f"REFUSED: no CRSP daily parquet for {start_year}-{end_year} under "
            f"{WRDS}")
    if smoke:
        present = present[-3:]
    daily = load_daily(present)
    tape = Tape(daily)
    sess = tape.di
    month = tape.month_of[sess]
    # the LAST session of each month on the tape
    last_of_month: dict[str, int] = {}
    for i, m in enumerate(tape.month_of):
        last_of_month[str(m)] = i
    anchors = np.array(sorted(last_of_month.values()), dtype="int64")
    is_anchor = np.zeros(tape.n, dtype=bool)
    is_anchor[anchors] = True
    keep = is_anchor[sess]
    uni = pd.DataFrame({
        "permno": daily["permno"].to_numpy()[keep].astype("int64"),
        "sess": sess[keep].astype("int64"),
        "month": month[keep],
        "cap_usd": tape.cap[keep],
        "prc": tape.prc[keep],
    })
    uni = uni[np.isfinite(uni["prc"].to_numpy()) & (uni["prc"].to_numpy() > 0)]
    uni["year"] = uni["month"].str.slice(0, 4).astype(int)
    uni["band"] = _band_of(uni["cap_usd"].to_numpy(dtype="float64"))
    block = {
        "price_source": [str((WRDS / f"crsp_dsf_{y}.parquet").relative_to(REPO))
                         for y in present],
        "years": [int(present[0]), int(present[-1])],
        "n_sessions": int(tape.n),
        "n_month_anchors": int(len(anchors)),
        "anchor_rule": ("the LAST SESSION of each calendar month on the CRSP "
                        "daily tape; the score is read at that close and the "
                        "forward return starts the NEXT session"),
        "cap_rule": (f"CRSP |prc| x shrout x 1000 at the anchor session, banded "
                     f"by the LIVE thresholds small<=${config.SIGNAL_UNIVERSE_SMALL_MAX_USD:,.0f} "
                     f"mid<=${config.SIGNAL_UNIVERSE_MID_MAX_USD:,.0f} "
                     f"(config.SIGNAL_UNIVERSE_*_MAX_USD). Nominal 2026 dollars "
                     f"applied to every year — the anachronism the live engine "
                     f"also commits, committed identically here so the "
                     f"calibration measures the universe the engine can "
                     f"reproduce"),
        "rows": int(len(uni)),
        "n_permnos": int(uni["permno"].nunique()),
    }
    return tape, uni.reset_index(drop=True), block


def attach_forward(tape: Any, panel: pd.DataFrame,
                   horizons) -> tuple[pd.DataFrame, dict]:
    """Forward compounded returns at each horizon, or NaN with a counted reason.

    A name whose CRSP block ends before `anchor + h` gets NaN at that horizon.
    The CRSP daily file carries no delisting return, so those are exactly the
    names that stopped trading — dropping them removes some of the WORST
    outcomes and biases every decile mean UP. The count is on the receipt; the
    direction is stated here so nobody has to infer it.
    """
    ret = np.clip(tape.ret, -0.999999, None)
    n = len(panel)
    cols = {int(h): np.full(n, np.nan) for h in horizons}
    missing = {int(h): 0 for h in horizons}
    order = np.argsort(panel["permno"].to_numpy(), kind="mergesort")
    pn = panel["permno"].to_numpy()[order]
    ses = panel["sess"].to_numpy()[order].astype("int64")
    if n == 0:
        for h in horizons:
            panel[f"fwd_{int(h)}"] = cols[int(h)]
        return panel, {"n_missing_forward_bar": missing}
    starts = np.flatnonzero(np.r_[True, pn[1:] != pn[:-1]])
    ends = np.r_[starts[1:], len(pn)]
    for s0, e0 in zip(starts, ends):
        blk = tape.blocks.get(int(pn[s0]))
        if blk is None:
            for h in horizons:
                missing[int(h)] += int(e0 - s0)
            continue
        bs, be = blk
        di = tape.di[bs:be].astype("int64")
        cum = np.concatenate(([0.0], np.cumsum(np.log1p(ret[bs:be]))))
        anchors = ses[s0:e0]
        a = np.searchsorted(di, anchors)
        safe_a = np.minimum(a, len(di) - 1)
        ok_a = (a < len(di)) & (di[safe_a] == anchors)
        tgt = panel.index.to_numpy()[order[s0:e0]]
        for h in horizons:
            hh = int(h)
            b = np.searchsorted(di, anchors + hh, side="right") - 1
            ok = ok_a & (b > a) & (di[-1] >= anchors + hh)
            idx = np.flatnonzero(ok)
            missing[hh] += int(len(anchors) - len(idx))
            if len(idx) == 0:
                continue
            r = np.exp(cum[b[idx] + 1] - cum[a[idx] + 1]) - 1.0
            cols[hh][tgt[idx]] = r
    for h in horizons:
        panel[f"fwd_{int(h)}"] = cols[int(h)]
    return panel, {
        "n_missing_forward_bar": missing,
        "basis": ("a name whose CRSP block ends before anchor+h contributes "
                  "nothing at that horizon; CRSP dsf carries no delisting "
                  "return, so this DROPS the worst outcomes and biases every "
                  "decile mean upward"),
    }


# ===========================================================================
# THE PANEL BUILDERS — one per leadable signal, each PIT or absent
# ===========================================================================


def _jkp_files() -> list[Path]:
    out = []
    if JKP_LATE.exists():
        out.append(JKP_LATE)
    if JKP_FULL.is_dir():
        out.extend(sorted(JKP_FULL.glob("jkp_usa_*.parquet")))
    return out


def build_profitability_panel(uni: pd.DataFrame, *, start_year: int,
                              smoke: bool = False) -> tuple[Optional[pd.DataFrame], dict]:
    """`quality` = Novy-Marx gross profit / assets, from the JKP characteristics.

    The live funnel computes `gross_profitability = grossMargin x assetTurnover`
    (`opportunity_funnel._fundamentals`), which is gross profit / assets. JKP's
    `gp_at` is that same ratio, stamped at `eom` — the meta files declare
    `pit_knowledge_column: eom (JKP formation stamping; spot-audit PASS
    2026-08-22)`, which is what makes the anchor legitimate.
    """
    files = _jkp_files()
    if not files:
        return None, {
            "verdict": NO_PANEL,
            "why": (f"no JKP characteristics parquet on this checkout: looked "
                    f"for {JKP_LATE.relative_to(REPO)} and "
                    f"{JKP_FULL.relative_to(REPO)}/jkp_usa_*.parquet"),
            "looked_for": [str(JKP_LATE.relative_to(REPO)),
                           str((JKP_FULL / 'jkp_usa_*.parquet').relative_to(REPO))],
        }
    frames = []
    used = []
    for p in files:
        try:
            d = pd.read_parquet(p, columns=["permno", "eom", "gp_at"])
        except (OSError, ValueError, KeyError) as exc:  # noqa: PERF203
            continue
        d = d[d["permno"].notna() & d["gp_at"].notna()]
        if d.empty:
            continue
        d["eom"] = pd.to_datetime(d["eom"])
        d = d[d["eom"].dt.year >= int(start_year)]
        if d.empty:
            continue
        frames.append(pd.DataFrame({
            "permno": d["permno"].to_numpy().astype("int64"),
            "month": d["eom"].dt.strftime("%Y-%m").to_numpy(),
            "score": d["gp_at"].to_numpy(dtype="float64"),
        }))
        used.append(str(p.relative_to(REPO)))
    if not frames:
        return None, {
            "verdict": NO_PANEL,
            "why": (f"the JKP parquet exists but carries no `gp_at` row at or "
                    f"after {start_year}"),
            "looked_for": [str(p.relative_to(REPO)) for p in files],
        }
    raw = pd.concat(frames, ignore_index=True)
    raw = raw.drop_duplicates(subset=["permno", "month"], keep="last")
    out = uni.merge(raw, on=["permno", "month"], how="inner")
    return out, {
        "sources": used,
        "score_formula": "gp_at (JKP) = gross profit / assets, Novy-Marx",
        "live_equivalent": ("opportunity_funnel._fundamentals: "
                            "grossMarginTTM/100 x assetTurnoverTTM, the same "
                            "ratio from a different vendor"),
        "pit_basis": ("JKP `eom` formation stamping; the meta files declare "
                      "pit_knowledge_column: eom, spot-audit PASS 2026-08-22"),
        "n_rows": int(len(out)),
    }


def build_insider_panel(uni: pd.DataFrame, *, start_year: int,
                        smoke: bool = False) -> tuple[Optional[pd.DataFrame], dict]:
    """`insider_score` = distinct open-market buyers + tanh(buy $ / $1M).

    The LIVE formula, reproduced exactly
    (`insider_trading.compute_opportunistic_buy_score`), over the same
    `lookback_days` the funnel passes. The panel is the SEC Form 4 bulk table,
    which stamps `observed_at_utc` as FILING_DATE_EOD_CONSERVATIVE — the filing
    date, not the trade date — so a score at an anchor uses only filings that
    were public at that close.

    ONE construction difference from the live path, and it is printed rather
    than smoothed: the bulk panel's `insider_open_market_buy` family already
    excludes 10b5-1 plan sales/purchases, while the live Finnhub path has no
    such field and cannot. The historical score is therefore the cleaner of the
    two, and a map fit on it is being applied to a slightly noisier live score.
    """
    if not SEC_INSIDER.exists():
        return None, {
            "verdict": NO_PANEL,
            "why": (f"no SEC Form 4 event panel on this checkout: looked for "
                    f"{SEC_INSIDER.relative_to(REPO)}"),
            "looked_for": [str(SEC_INSIDER.relative_to(REPO))],
        }
    cols = ["permno", "event_type", "observed_at_utc", "insider_cik",
            "insider_dollar_value"]
    d = pd.read_parquet(SEC_INSIDER, columns=cols)
    d = d[d["event_type"] == "insider_open_market_buy"]
    d = d[d["permno"].notna() & d["observed_at_utc"].notna()]
    if d.empty:
        return None, {
            "verdict": NO_PANEL,
            "why": (f"{SEC_INSIDER.relative_to(REPO)} carries no "
                    f"`insider_open_market_buy` row"),
            "looked_for": [str(SEC_INSIDER.relative_to(REPO))],
        }
    d["permno"] = d["permno"].to_numpy().astype("int64")
    obs = pd.to_datetime(d["observed_at_utc"], utc=True).dt.tz_localize(None)
    d = d.assign(obs=obs)
    lookback = int(config.CALIB_INSIDER_LOOKBACK_DAYS)

    # anchor calendar dates, one per month, from the tape's month labels
    anchors = (uni[["month"]].drop_duplicates().sort_values("month")
               .reset_index(drop=True))
    anchors["anchor_dt"] = (pd.PeriodIndex(anchors["month"], freq="M")
                            .to_timestamp(how="end").normalize())
    rows = []
    for m, adt in zip(anchors["month"].to_numpy(),
                      anchors["anchor_dt"].to_numpy()):
        lo = pd.Timestamp(adt) - pd.Timedelta(days=lookback)
        w = d[(d["obs"] > lo) & (d["obs"] <= pd.Timestamp(adt))]
        if w.empty:
            continue
        g = w.groupby("permno").agg(
            n_buyers=("insider_cik", "nunique"),
            buy_value=("insider_dollar_value", "sum"))
        rows.append(pd.DataFrame({
            "permno": g.index.to_numpy().astype("int64"),
            "month": np.full(len(g), m, dtype=object),
            "n_buyers": g["n_buyers"].to_numpy(dtype="float64"),
            "buy_value": np.nan_to_num(
                g["buy_value"].to_numpy(dtype="float64"), nan=0.0),
        }))
    if not rows:
        return None, {
            "verdict": NO_PANEL,
            "why": ("the Form 4 panel exists but no open-market buy falls in "
                    "any anchor's lookback window on this tape"),
            "looked_for": [str(SEC_INSIDER.relative_to(REPO))],
        }
    buys = pd.concat(rows, ignore_index=True)
    from backend.services.insider_trading import VALUE_SCALE_USD
    buys["score"] = (buys["n_buyers"]
                     + np.tanh(buys["buy_value"] / float(VALUE_SCALE_USD)))
    out = uni.merge(buys[["permno", "month", "score"]],
                    on=["permno", "month"], how="left")
    # A name with a defined feed and no purchase scores 0.0 — the LIVE
    # semantics (`compute_opportunistic_buy_score`'s `empty` branch:
    # available=True, opp_score=0.0). Missing is not what this is; zero is.
    n_zero = int(out["score"].isna().sum())
    out["score"] = out["score"].fillna(0.0)
    return out, {
        "sources": [str(SEC_INSIDER.relative_to(REPO))],
        "score_formula": (f"n_distinct_open_market_buyers + "
                          f"tanh(buy_value / ${float(VALUE_SCALE_USD):,.0f}) "
                          f"over a {lookback}-calendar-day lookback — the LIVE "
                          f"formula, insider_trading."
                          f"compute_opportunistic_buy_score"),
        "pit_basis": ("observed_at_utc = FILING_DATE_EOD_CONSERVATIVE on the "
                      "bulk panel: the FILING date, never the trade date"),
        "construction_difference_from_live": (
            "the bulk panel's insider_open_market_buy family excludes 10b5-1 "
            "plan transactions; the live Finnhub path has no such field and "
            "cannot. The historical score is the cleaner of the two"),
        "n_scored_zero_no_buy_in_window": n_zero,
        "n_rows": int(len(out)),
    }


def build_fusion_panel(uni: pd.DataFrame, *, start_year: int,
                       smoke: bool = False) -> tuple[Optional[pd.DataFrame], dict]:
    """BRAIN-007's frozen equal-weight z-composite of the other two legs.

    Both legs must be present for a name-month: the fusion signal's own
    `missing_reason` is "fusion signal needs both insider and profitability
    legs", and a composite computed from one leg would be that leg wearing the
    composite's name.
    """
    prof, pmeta = build_profitability_panel(uni, start_year=start_year,
                                            smoke=smoke)
    ins, imeta = build_insider_panel(uni, start_year=start_year, smoke=smoke)
    if prof is None or ins is None:
        missing = []
        if prof is None:
            missing.append(f"profitability leg: {pmeta.get('why')}")
        if ins is None:
            missing.append(f"insider leg: {imeta.get('why')}")
        return None, {
            "verdict": NO_PANEL,
            "why": ("the fusion composite needs BOTH legs and one is absent: "
                    + " ; ".join(missing)),
            "looked_for": sorted(set(list(pmeta.get("looked_for") or [])
                                     + list(imeta.get("looked_for") or []))),
        }
    a = prof[["permno", "month", "sess", "cap_usd", "prc", "year", "band",
              "score"]].rename(columns={"score": "leg_quality"})
    b = ins[["permno", "month", "score"]].rename(columns={"score": "leg_insider"})
    out = a.merge(b, on=["permno", "month"], how="inner")
    if out.empty:
        return None, {
            "verdict": NO_PANEL,
            "why": "the two legs share no (permno, month) on this checkout",
            "looked_for": sorted(set(list(pmeta.get("looked_for") or [])
                                     + list(imeta.get("looked_for") or []))),
        }
    for leg in ("leg_quality", "leg_insider"):
        g = out.groupby("month")[leg]
        mu = g.transform("mean")
        sd = g.transform("std")
        out[f"z_{leg}"] = np.where(sd.to_numpy() > 0,
                                   (out[leg].to_numpy() - mu.to_numpy())
                                   / np.where(sd.to_numpy() > 0,
                                              sd.to_numpy(), 1.0), 0.0)
    out["score"] = 0.5 * (out["z_leg_quality"] + out["z_leg_insider"])
    return out.drop(columns=["z_leg_quality", "z_leg_insider"]), {
        "sources": sorted(set(list(pmeta.get("sources") or [])
                              + list(imeta.get("sources") or []))),
        "score_formula": ("equal-weight mean of the two legs' CROSS-SECTIONAL "
                          "z-scores within the anchor month — BRAIN-007's "
                          "frozen composite"),
        "pit_basis": (f"quality: {pmeta.get('pit_basis')} ; insider: "
                      f"{imeta.get('pit_basis')}"),
        "n_rows": int(len(out)),
    }


PANEL_BUILDERS: dict[str, Callable] = {
    "profitability_small": build_profitability_panel,
    "insider_opportunistic": build_insider_panel,
    "fusion_insider_profitability": build_fusion_panel,
}


# ===========================================================================
# THE STATISTICS
# ===========================================================================


def assign_deciles(panel: pd.DataFrame, *, first_test_year: int,
                   n_deciles: Optional[int] = None
                   ) -> tuple[pd.DataFrame, dict]:
    """Walk-forward decile assignment: cut points from the PAST only.

    Ties go DOWN (`side="left"`), so a score every name shares — the insider
    score is 0.0 for every name with no open-market Form 4 in its lookback —
    lands in ONE decile rather than being split across nine by cut points that
    cannot separate it. The number of non-empty deciles is reported, because a
    map with two levels is not a map with ten and the reader must be able to
    see which one this is.
    """
    k = int(n_deciles if n_deciles is not None else config.CALIB_N_DECILES)
    years = panel["year"].to_numpy()
    scores = panel["score"].to_numpy(dtype="float64")
    dec = np.zeros(len(panel), dtype="int64")
    cuts_by_year: dict[str, list] = {}
    qs = np.linspace(0.0, 1.0, k + 1)[1:-1]
    for y in sorted({int(v) for v in years if int(v) >= int(first_test_year)}):
        train = scores[years < y]
        train = train[np.isfinite(train)]
        if len(train) < k * int(config.CALIB_MIN_NAMES_PER_DECILE):
            continue
        cuts = np.quantile(train, qs)
        cuts_by_year[str(y)] = [round(float(c), 10) for c in cuts]
        m = years == y
        dec[m] = np.searchsorted(cuts, scores[m], side="left") + 1
    panel = panel.copy()
    panel["decile"] = dec
    oos = panel[panel["decile"] > 0].copy()
    live = scores[np.isfinite(scores)]
    cut_live = ([round(float(c), 10) for c in np.quantile(live, qs)]
                if len(live) >= k * int(config.CALIB_MIN_NAMES_PER_DECILE)
                else None)
    nonempty = sorted(int(x) for x in set(oos["decile"].to_numpy()))
    tie = 0.0
    if len(oos):
        vc = oos["decile"].value_counts()
        tie = float(vc.max()) / float(len(oos))
    return oos, {
        "n_deciles": k,
        "first_test_year": int(first_test_year),
        "refit": "yearly, expanding window, cut points from years strictly < y",
        "tie_rule": "side='left' — a tied block falls into ONE decile",
        "cut_points_by_year": cuts_by_year,
        "cut_points_live": cut_live,
        "cut_points_live_basis": (
            "quantiles of the score over the WHOLE panel. These are the cut "
            "points `roi_rank` maps a live candidate's raw score through; they "
            "are a scaling of the score's own distribution and carry no "
            "forward return, so fitting them on all years leaks nothing into "
            "the decile TABLE, every cell of which is out-of-sample"),
        "n_oos_rows": int(len(oos)),
        "n_train_only_rows": int(len(panel) - len(oos)),
        "nonempty_deciles": nonempty,
        "n_nonempty_deciles": len(nonempty),
        "largest_decile_share": round(tie, 6),
    }


def _nw_t_local(x: np.ndarray, lag: int) -> Optional[float]:
    from scripts.night_factory_jobs import _nw_t
    return _nw_t(x, int(max(1, lag)))


def _norm_sf(z: float) -> float:
    """Two-sided normal p. `math.erfc` — no scipy dependency on this path."""
    return float(math.erfc(abs(float(z)) / math.sqrt(2.0)))


def _spearman(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if len(x) < 3:
        return None
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    sx, sy = rx.std(), ry.std()
    if sx <= 0 or sy <= 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _abnormal(oos: pd.DataFrame, h: int) -> np.ndarray:
    col = f"fwd_{int(h)}"
    r = oos[col].to_numpy(dtype="float64")
    mkt = oos.groupby("sess")[col].transform("mean").to_numpy(dtype="float64")
    return r - mkt


def cost_pct_for(tau: Optional[float], h: int) -> Optional[float]:
    """The declared round-trip cost of holding one decile for h sessions.

    A one-way monthly turnover of tau means tau of the book is SOLD and BOUGHT
    each month, so the monthly charge is `2 x tau x CALIB_COST_BPS_PER_SIDE`;
    the horizon scales it by h/21. Returned as a FRACTION. None when the
    turnover could not be computed — missing is missing, and the caller prints
    it rather than charging zero.
    """
    if tau is None:
        return None
    per_month = 2.0 * float(tau) * float(config.CALIB_COST_BPS_PER_SIDE) / 10_000.0
    return per_month * float(h) / float(config.CALIB_SESSIONS_PER_MONTH)


def decile_table(oos: pd.DataFrame, h: int, *, rng: np.random.Generator,
                 taus: Optional[dict] = None) -> dict:
    """One horizon's decile table, with a monthly block-bootstrap CI per cell.

    Every cell carries BOTH a gross mean and a NET mean: `roi_rank` sizes on the
    net one, because "costs are never omitted" is one of the four things
    EXPLORE DIRTY, PROMOTE CLEAN does not relax, and a per-name mu quoted gross
    would be the family-average defect with a decile's clothes on.
    """
    abn = _abnormal(oos, h)
    ok = np.isfinite(abn)
    df = pd.DataFrame({
        "decile": oos["decile"].to_numpy()[ok],
        "month": oos["month"].to_numpy()[ok],
        "abn": abn[ok],
    })
    months = np.array(sorted(set(df["month"].tolist())))
    draws = int(config.CALIB_BOOTSTRAP_DRAWS)
    pct = float(config.CALIB_DOWNSIDE_PCTILE)
    rows = []
    by_month_mean = {}
    for d, g in df.groupby("decile"):
        vals = g["abn"].to_numpy(dtype="float64")
        mm = g.groupby("month")["abn"].mean()
        by_month_mean[int(d)] = mm
        boot = np.empty(draws)
        idx_by_month = {m: mm.get(m, np.nan) for m in months}
        base = np.array([idx_by_month[m] for m in months], dtype="float64")
        base_ok = base[np.isfinite(base)]
        if len(base_ok) >= 2:
            pick = rng.integers(0, len(base_ok), size=(draws, len(base_ok)))
            boot = base_ok[pick].mean(axis=1)
            lo, hi = np.percentile(boot, [2.5, 97.5])
        else:
            lo = hi = float("nan")
        tau = (taus or {}).get(int(d))
        c = cost_pct_for(tau, h)
        mean_g = float(np.mean(vals))
        rows.append({
            "decile": int(d),
            "n_names": int(len(vals)),
            "n_date_blocks": int(mm.notna().sum()),
            "turnover_one_way_monthly": (round(float(tau), 6)
                                         if tau is not None else None),
            "cost_pct": round(100.0 * c, 6) if c is not None else None,
            "mean_abn_net_pct": (round(100.0 * (mean_g - c), 6)
                                 if c is not None else None),
            "mean_abn_pct": round(100.0 * float(np.mean(vals)), 6),
            "p20_abn_pct": round(100.0 * float(np.percentile(vals, pct)), 6),
            "sd_abn_pct": round(100.0 * float(np.std(vals, ddof=1))
                                if len(vals) > 1 else float("nan"), 6),
            "ci_lo_pct": round(100.0 * float(lo), 6) if np.isfinite(lo) else None,
            "ci_hi_pct": round(100.0 * float(hi), 6) if np.isfinite(hi) else None,
            # The SAME interval shifted by this decile's own cost, so a reader
            # never sees a net mean printed beside a gross interval it appears
            # to sit outside. The cost is a constant, so the WIDTH — and
            # therefore the standard error the explorer's posterior derives
            # from it — is identical either way.
            "ci_lo_net_pct": (round(100.0 * (float(lo) - c), 6)
                              if (np.isfinite(lo) and c is not None) else None),
            "ci_hi_net_pct": (round(100.0 * (float(hi) - c), 6)
                              if (np.isfinite(hi) and c is not None) else None),
        })
    rows.sort(key=lambda r: r["decile"])
    return {"rows": rows, "_by_month_mean": by_month_mean,
            "n_date_blocks": int(len(months))}


def turnover(oos: pd.DataFrame, decile: int) -> Optional[float]:
    """Mean one-way monthly turnover of the named decile's membership."""
    g = oos[oos["decile"] == int(decile)]
    if g.empty:
        return None
    members = {m: set(x.tolist()) for m, x in
               g.groupby("month")["permno"]}
    months = sorted(members)
    taus = []
    for prev, cur in zip(months, months[1:]):
        now = members[cur]
        if not now:
            continue
        taus.append(len(now - members[prev]) / float(len(now)))
    return float(np.mean(taus)) if taus else None


def spread_block(oos: pd.DataFrame, h: int, table: dict,
                 taus: Optional[dict] = None) -> dict:
    """D_hi − D_lo per month, gross and net, with a Newey-West t on each."""
    rows = table["rows"]
    nonempty = [r["decile"] for r in rows
                if r["n_names"] >= int(config.CALIB_MIN_NAMES_PER_DECILE)]
    if len(nonempty) < 2:
        return {"verdict": (f"{REFUSED}: fewer than two deciles carry "
                            f"{config.CALIB_MIN_NAMES_PER_DECILE} names at "
                            f"horizon {h}")}
    d_lo, d_hi = min(nonempty), max(nonempty)
    mm = table["_by_month_mean"]
    lo_s, hi_s = mm.get(d_lo), mm.get(d_hi)
    idx = sorted(set(lo_s.index) & set(hi_s.index))
    if len(idx) < int(config.CALIB_MIN_BLOCKS):
        return {"verdict": (f"{REFUSED}: only {len(idx)} month blocks carry "
                            f"both decile {d_lo} and decile {d_hi} at horizon "
                            f"{h}, below CALIB_MIN_BLOCKS "
                            f"{config.CALIB_MIN_BLOCKS}"),
                "n_date_blocks": int(len(idx))}
    series = np.array([hi_s[m] - lo_s[m] for m in idx], dtype="float64")
    lag = int(math.ceil(float(h) / float(config.CALIB_SESSIONS_PER_MONTH)))
    t_gross = _nw_t_local(series, lag)
    bps = float(config.CALIB_COST_BPS_PER_SIDE)
    taus = taus or {}
    tau_lo = taus.get(int(d_lo), turnover(oos, d_lo))
    tau_hi = taus.get(int(d_hi), turnover(oos, d_hi))
    if tau_lo is None or tau_hi is None:
        cost_h = None
    else:
        per_month = (tau_lo + tau_hi) * 2.0 * bps / 10_000.0
        cost_h = per_month * float(h) / float(config.CALIB_SESSIONS_PER_MONTH)
    net = series - (cost_h or 0.0)
    t_net = _nw_t_local(net, lag)
    return {
        "decile_low": int(d_lo),
        "decile_high": int(d_hi),
        "label": f"D{d_hi} - D{d_lo}",
        "n_date_blocks": int(len(idx)),
        "nw_lag_months": lag,
        "gross_spread_pct": round(100.0 * float(series.mean()), 6),
        "gross_t": round(float(t_gross), 4) if t_gross is not None else None,
        "cost_pct": (round(100.0 * float(cost_h), 6)
                     if cost_h is not None else None),
        "cost_basis": (
            f"one-way monthly turnover D{d_lo} {tau_lo if tau_lo is None else round(tau_lo, 4)} "
            f"+ D{d_hi} {tau_hi if tau_hi is None else round(tau_hi, 4)}, each "
            f"replaced slice SOLD and BOUGHT at {bps:g} bps/side = "
            f"2 x tau x {bps:g} bps per month, scaled to the horizon by "
            f"{h}/{config.CALIB_SESSIONS_PER_MONTH:g} months "
            f"(config.CALIB_COST_BPS_PER_SIDE)"),
        "net_spread_pct": round(100.0 * float(net.mean()), 6),
        "net_t": round(float(t_net), 4) if t_net is not None else None,
        "net_p_two_sided": (round(_norm_sf(t_net), 8)
                            if t_net is not None else None),
        "monthly_series_head": [round(float(v), 8) for v in series[:5].tolist()],
        "monthly_series_tail": [round(float(v), 8) for v in series[-5:].tolist()],
        "tail_before_mean": {
            "worst_month_pct": round(100.0 * float(series.min()), 6),
            "best_month_pct": round(100.0 * float(series.max()), 6),
            "share_of_months_positive": round(
                float((series > 0).mean()), 6),
            "top5_months_share_of_total": round(
                float(np.sort(series)[-5:].sum() / series.sum())
                if abs(series.sum()) > 1e-12 else float("nan"), 6),
        },
    }


def monotonicity(table: dict) -> dict:
    rows = [r for r in table["rows"]
            if r["n_names"] >= int(config.CALIB_MIN_NAMES_PER_DECILE)]
    n = len(rows)
    floor = int(config.CALIB_MIN_NONEMPTY_DECILES)
    if n < floor:
        return {"monotone": None, "n_nonempty_deciles": n,
                "verdict": (
                    f"CANNOT DETERMINE: only {n} decile(s) carry "
                    f"{config.CALIB_MIN_NAMES_PER_DECILE}+ names, below "
                    f"CALIB_MIN_NONEMPTY_DECILES {floor}. A Spearman over "
                    f"{n} points is not a monotonicity test, so this signal "
                    f"cannot reach CALIBRATED on this panel — the conservative "
                    f"direction: EXPLORE still funds it, EXPLOIT does not")}
    rho = _spearman(np.array([r["decile"] for r in rows], dtype="float64"),
                    np.array([r["mean_abn_pct"] for r in rows], dtype="float64"))
    thr = float(config.CALIB_MONOTONE_MIN_SPEARMAN)
    return {
        "spearman_decile_vs_mean": round(rho, 6) if rho is not None else None,
        "threshold": thr,
        "n_nonempty_deciles": n,
        "monotone": bool(rho is not None and rho >= thr),
        "verdict": (f"Spearman {rho:.3f} over {n} non-empty deciles against a "
                    f"CALIB_MONOTONE_MIN_SPEARMAN of {thr:g}"
                    if rho is not None else "CANNOT DETERMINE: no rank variance"),
    }


def run_nulls(panel: pd.DataFrame, *, first_test_year: int, h: int,
              rng: np.random.Generator, draws: Optional[int] = None) -> dict:
    """The two null tests. Both are the SAME shuffle; one point, one distribution."""
    n_draws = int(draws if draws is not None else config.CALIB_NULL_DRAWS)
    sess = panel["sess"].to_numpy()
    scores = panel["score"].to_numpy(dtype="float64")

    def shuffled(seed_rng: np.random.Generator) -> np.ndarray:
        out = scores.copy()
        order = np.argsort(sess, kind="mergesort")
        s = sess[order]
        starts = np.flatnonzero(np.r_[True, s[1:] != s[:-1]])
        ends = np.r_[starts[1:], len(s)]
        for a, b in zip(starts, ends):
            idx = order[a:b]
            out[idx] = scores[seed_rng.permutation(idx)]
        return out

    # NULL 1 — the whole pipeline on ONE shuffled panel: cut points refit on
    # the shuffled training window, decile table rebuilt, spread recomputed.
    p1 = panel.copy()
    p1["score"] = shuffled(rng)
    oos1, meta1 = assign_deciles(p1, first_test_year=first_test_year)
    if len(oos1) == 0:
        one = {"verdict": f"{REFUSED}: the shuffled panel produced no test rows"}
    else:
        t1 = decile_table(oos1, h, rng=rng)
        s1 = spread_block(oos1, h, t1)
        m1 = monotonicity(t1)
        one = {
            "gross_spread_pct": s1.get("gross_spread_pct"),
            "gross_t": s1.get("gross_t"),
            "cost_pct": s1.get("cost_pct"),
            "net_spread_pct": s1.get("net_spread_pct"),
            "net_t": s1.get("net_t"),
            "spearman": m1.get("spearman_decile_vs_mean"),
            "n_nonempty_deciles": m1.get("n_nonempty_deciles"),
            "label": s1.get("label"),
            "basis": ("scores permuted WITHIN each anchor date; cut points "
                      "refit on the shuffled training window; the entire "
                      "decile table rebuilt. This is the review's '(a) "
                      "shuffled scores within date' and '(b) the map fit on "
                      "the shuffled panel' — they are one operation and are "
                      "named as one rather than dressed as two"),
            "read_the_gross": (
                "READ THE GROSS LINE. A shuffled decile turns over ~100% every "
                "month, so its NET is the gross minus a cost constant near "
                "1%/month and its net t is large and negative by construction. "
                "That is a fact about random rebalancing, not about the "
                "shuffle: the null's claim is that the GROSS spread is zero"),
        }

    # NULL 2 — the same shuffle many times on the OOS panel, for a DISTRIBUTION.
    oos_real, _ = assign_deciles(panel, first_test_year=first_test_year)
    dist_spread: list[float] = []
    dist_rho: list[float] = []
    if len(oos_real):
        abn = _abnormal(oos_real, h)
        keep = np.isfinite(abn)
        base = pd.DataFrame({
            "sess": oos_real["sess"].to_numpy()[keep],
            "decile": oos_real["decile"].to_numpy()[keep],
            "abn": abn[keep],
        })
        dec = base["decile"].to_numpy()
        ss = base["sess"].to_numpy()
        order = np.argsort(ss, kind="mergesort")
        s_sorted = ss[order]
        starts = np.flatnonzero(np.r_[True, s_sorted[1:] != s_sorted[:-1]])
        ends = np.r_[starts[1:], len(s_sorted)]
        groups = [order[a:b] for a, b in zip(starts, ends)]
        nonempty = sorted(set(int(x) for x in dec))
        d_lo, d_hi = min(nonempty), max(nonempty)
        abn_v = base["abn"].to_numpy(dtype="float64")
        for _ in range(n_draws):
            shuf = dec.copy()
            for idx in groups:
                shuf[idx] = dec[rng.permutation(idx)]
            means = (pd.Series(abn_v).groupby(pd.Series(shuf)).mean())
            if d_lo in means.index and d_hi in means.index:
                dist_spread.append(float(means[d_hi] - means[d_lo]))
            rho = _spearman(means.index.to_numpy(dtype="float64"),
                            means.to_numpy(dtype="float64"))
            if rho is not None:
                dist_rho.append(float(rho))
    two = {
        "draws": n_draws,
        "n_spread_draws": len(dist_spread),
        "spread_mean_pct": (round(100.0 * float(np.mean(dist_spread)), 6)
                            if dist_spread else None),
        "spread_sd_pct": (round(100.0 * float(np.std(dist_spread, ddof=1)), 6)
                          if len(dist_spread) > 1 else None),
        "spread_p95_pct": (round(100.0 * float(np.percentile(dist_spread, 95)), 6)
                           if dist_spread else None),
        "spearman_p95": (round(float(np.percentile(dist_rho, 95)), 6)
                         if dist_rho else None),
        "basis": ("the same within-date shuffle repeated on the OUT-OF-SAMPLE "
                  "panel, giving the distribution the real spread is placed "
                  "against. A spread inside this distribution is not a spread, "
                  "whatever its t"),
        "compared_on": (
            "GROSS against GROSS. The shuffled draws carry no cost (they are "
            "decile means, not a traded book), so placing a NET spread against "
            "them would charge one side of the comparison and not the other"),
        "_spread_draws": [float(x) for x in dist_spread],
    }
    return {"null_1_end_to_end_shuffle": one, "null_2_shuffled_distribution": two}


# ===========================================================================
# ONE SIGNAL
# ===========================================================================


def calibrate_signal(signal_id: str, tape: Any, uni: pd.DataFrame, *,
                     uni_block: dict, start_year: int, smoke: bool = False,
                     registry: Any = None) -> dict:
    """Everything about one signal except its Holm p, which is a FAMILY fact."""
    horizons = [int(h) for h in config.CALIB_HORIZONS_SESSIONS]
    bands, uni_str = licensed_bands(signal_id, registry=registry)
    builder = PANEL_BUILDERS.get(signal_id)
    base = {
        "schema": SCHEMA,
        "signal": signal_id,
        "asof": RUN_DATE,
        "generated_utc": _now(),
        "licence": "PRODUCT_EXPERIMENT",
        "roadmap_item": "chunk 22",
        "source": ("docs/research_notes/2026-09-20/"
                   "feedback_murat_review_2026-09-20_evening.md issue 1"),
        "deciding_horizon_sessions": int(config.CALIB_DECIDING_HORIZON_SESSIONS),
        "horizons_sessions": horizons,
        "licensed_universe": uni_str,
        "licensed_bands": sorted(bands),
        "smoke": bool(smoke),
    }
    if builder is None:
        base.update({
            "verdict": NO_PANEL,
            "verdict_basis": (
                f"{signal_id} may LEAD a ranking and NO point-in-time score "
                f"panel is wired for it in "
                f"scripts/calibrate_signal_return.PANEL_BUILDERS. There is "
                f"nothing on disk from which its score can be recomputed "
                f"historically, so it gets no map — never a guess"),
            "looked_for": [],
        })
        return base
    if not bands:
        base.update({
            "verdict": REFUSED,
            "verdict_basis": (
                f"the registry records {signal_id}'s universe as {uni_str!r}, "
                f"which config.SIGNAL_UNIVERSE_BANDS maps to no cap band — "
                f"there is no cross-sectional stock universe to calibrate on"),
        })
        return base

    panel, meta = builder(uni, start_year=start_year, smoke=smoke)
    if panel is None:
        base.update({
            "verdict": meta.get("verdict", NO_PANEL),
            "verdict_basis": meta.get("why"),
            "looked_for": meta.get("looked_for") or [],
        })
        return base
    panel = panel[np.isin(panel["band"].to_numpy(), sorted(bands))].copy()
    panel = panel[np.isfinite(panel["score"].to_numpy(dtype="float64"))]
    panel = panel.reset_index(drop=True)
    if panel.empty:
        base.update({
            "verdict": REFUSED,
            "verdict_basis": (
                f"the panel exists and no row survives {signal_id}'s licensed "
                f"cap band(s) {sorted(bands)} ({uni_str})"),
            "panel": meta,
        })
        return base

    panel, fwd_meta = attach_forward(tape, panel, horizons)
    first_year = int(panel["year"].min())
    first_test_year = first_year + int(config.CALIB_FIRST_TEST_YEAR_OFFSET)
    oos, wf = assign_deciles(panel, first_test_year=first_test_year)
    rng = np.random.default_rng(int(config.CALIB_BOOTSTRAP_SEED))
    taus = {int(d): turnover(oos, int(d))
            for d in sorted({int(x) for x in oos["decile"].to_numpy()})}

    base["construction"] = {
        "universe": uni_block,
        "panel": meta,
        "forward": fwd_meta,
        "walk_forward": wf,
        "abnormal": ("the name's own compounded forward return minus the "
                     "EQUAL-WEIGHT mean of this signal's own scored universe "
                     "at the same anchor and horizon"),
        "block_unit": "calendar month (CANON §58: n_effective counts DATE BLOCKS)",
        "bootstrap": {"draws": int(config.CALIB_BOOTSTRAP_DRAWS),
                      "seed": int(config.CALIB_BOOTSTRAP_SEED),
                      "unit": "month blocks, resampled with replacement"},
        "cost_ruler_bps_per_side": float(config.CALIB_COST_BPS_PER_SIDE),
        "decile_turnover_one_way_monthly": {str(k): (round(float(v), 6)
                                                     if v is not None else None)
                                            for k, v in taus.items()},
    }
    base["cut_points"] = wf.get("cut_points_live")
    base["cut_points_basis"] = wf.get("cut_points_live_basis")

    if len(oos) == 0:
        base.update({
            "verdict": REFUSED,
            "verdict_basis": (
                f"the panel starts in {first_year} and the first test year is "
                f"{first_test_year} (+{config.CALIB_FIRST_TEST_YEAR_OFFSET}); "
                f"no row falls in a test year, so nothing out of sample exists "
                f"to calibrate on"),
        })
        return base

    per_h: dict[str, dict] = {}
    for h in horizons:
        table = decile_table(oos, h, rng=rng, taus=taus)
        spread = spread_block(oos, h, table, taus)
        mono = monotonicity(table)
        per_h[str(h)] = {
            "deciles": table["rows"],
            "n_date_blocks": table["n_date_blocks"],
            "spread": spread,
            "monotonicity": mono,
        }
    deciding = str(int(config.CALIB_DECIDING_HORIZON_SESSIONS))
    nulls = run_nulls(panel, first_test_year=first_test_year,
                      h=int(config.CALIB_DECIDING_HORIZON_SESSIONS), rng=rng,
                      draws=(10 if smoke else None))
    draws = nulls["null_2_shuffled_distribution"].pop("_spread_draws", [])
    real_gross = (per_h.get(deciding, {}).get("spread", {})
                  .get("gross_spread_pct"))
    n2 = nulls["null_2_shuffled_distribution"]
    n2["real_net_spread_pct"] = (per_h.get(deciding, {}).get("spread", {})
                                 .get("net_spread_pct"))
    n2["real_gross_spread_pct"] = real_gross
    if draws and real_gross is not None:
        arr = np.array(draws, dtype="float64") * 100.0
        n2["real_percentile_of_null"] = round(
            float((arr < float(real_gross)).mean()), 6)
    base["horizons"] = per_h
    base["nulls"] = nulls
    return base


def family_verdict(entry: dict, holm_adj: dict) -> dict:
    """The verdict, once the family's Holm adjustment exists."""
    if entry.get("verdict") in (NO_PANEL, REFUSED):
        return entry
    deciding = str(int(config.CALIB_DECIDING_HORIZON_SESSIONS))
    block = (entry.get("horizons") or {}).get(deciding) or {}
    spread = block.get("spread") or {}
    mono = block.get("monotonicity") or {}
    key = f"{entry['signal']}@{deciding}"
    p_adj = holm_adj.get(key)
    alpha = float(config.CALIB_HOLM_ALPHA)
    net = _f(spread.get("net_spread_pct"))
    entry["holm"] = {"key": key, "adjusted_p": p_adj, "alpha": alpha,
                     "family": sorted(holm_adj),
                     "basis": ("Holm-Bonferroni over every (signal x horizon) "
                               "spread this run computed — the EXPORT rule "
                               "(CANON §63), because this table SIZES "
                               "positions")}
    if net is None or p_adj is None:
        entry["verdict"] = REFUSED
        entry["verdict_basis"] = (
            f"no net spread or no p at the deciding horizon ({deciding} "
            f"sessions): {spread.get('verdict') or 'the spread block is empty'}")
        return entry
    sig = float(p_adj) < alpha
    if net > 0 and sig and mono.get("monotone") is True:
        entry["verdict"] = CALIBRATED
    elif net < 0 and sig:
        entry["verdict"] = INVERTED
    else:
        entry["verdict"] = WEAK
    entry["verdict_basis"] = (
        f"at {deciding} sessions the {spread.get('label')} NET spread is "
        f"{net:+.4f}% (gross {spread.get('gross_spread_pct')}%, cost "
        f"{spread.get('cost_pct')}%), NW t {spread.get('net_t')} over "
        f"{spread.get('n_date_blocks')} month blocks, Holm-adjusted p "
        f"{p_adj:.6g} against alpha {alpha:g}; monotonicity: "
        f"{mono.get('verdict')}. Verdict {entry['verdict']}: CALIBRATED needs "
        f"net > 0 AND Holm p < alpha AND monotone; INVERTED is net < 0 at Holm "
        f"p < alpha; everything else is WEAK and feeds EXPLORE's posterior "
        f"rather than EXPLOIT's capital")
    return entry


# ===========================================================================
# THE JOB
# ===========================================================================


def C7_signal_calibration(smoke: bool = False, run: int = 1,
                          resume: bool = False) -> dict:
    """The night job. Writes one JSON per signal; the file IS the cursor."""
    t0 = time.time()
    box_s = float(config.CALIB_TIME_BOX_MINUTES) * 60.0
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    lead, excluded = leadable_signals()
    start_year = int(config.CALIB_START_YEAR)
    end_year = int(RUN_DATE[:4])

    entries: dict[str, dict] = {}
    resumed: list[str] = []
    timed_out: list[str] = []
    if resume:
        for sid in lead:
            p = output_path(sid, smoke=smoke).with_suffix(".partial.json")
            if p.exists():
                try:
                    entries[sid] = json.loads(p.read_text(encoding="utf-8"))
                    resumed.append(sid)
                except (OSError, json.JSONDecodeError):
                    pass

    tape = uni = None
    uni_block: dict = {}
    todo = [s for s in lead if s not in entries]
    if todo:
        tape, uni, uni_block = build_universe(start_year=start_year,
                                              end_year=end_year, smoke=smoke)
    for sid in todo:
        if time.time() - t0 > box_s:
            timed_out.append(sid)
            entries[sid] = {
                "schema": SCHEMA, "signal": sid, "asof": RUN_DATE,
                "generated_utc": _now(), "verdict": REFUSED,
                "verdict_basis": (
                    f"the {config.CALIB_TIME_BOX_MINUTES:g}-minute box "
                    f"(config.CALIB_TIME_BOX_MINUTES) expired before this "
                    f"signal was reached. A refusal is a finding; an absent "
                    f"file would have been a silence"),
            }
            continue
        entries[sid] = calibrate_signal(sid, tape, uni, uni_block=uni_block,
                                        start_year=start_year, smoke=smoke)
        output_path(sid, smoke=smoke).with_suffix(".partial.json").write_text(
            json.dumps(entries[sid], indent=1, default=str), encoding="utf-8")

    # THE FAMILY: Holm over every (signal x horizon) spread that produced a p.
    pvals: dict[str, float] = {}
    for sid, e in entries.items():
        for hs, blk in (e.get("horizons") or {}).items():
            p = _f((blk.get("spread") or {}).get("net_p_two_sided"))
            if p is not None:
                pvals[f"{sid}@{hs}"] = p
    hb = holm(pvals, alpha=float(config.CALIB_HOLM_ALPHA)) if pvals else {}
    adj = dict(hb.get("adjusted") or {})

    written: dict[str, str] = {}
    for sid, e in entries.items():
        e = family_verdict(e, adj)
        e["holm_family"] = hb
        p = output_path(sid, smoke=smoke)
        p.write_text(json.dumps(e, indent=1, default=str), encoding="utf-8")
        written[sid] = str(p.relative_to(REPO))
        part = p.with_suffix(".partial.json")
        if part.exists():
            part.unlink()
        entries[sid] = e

    summary = {sid: {
        "verdict": e.get("verdict"),
        "net_spread_pct": ((e.get("horizons") or {})
                           .get(str(int(config.CALIB_DECIDING_HORIZON_SESSIONS)),
                                {}).get("spread", {}).get("net_spread_pct")),
        "net_t": ((e.get("horizons") or {})
                  .get(str(int(config.CALIB_DECIDING_HORIZON_SESSIONS)), {})
                  .get("spread", {}).get("net_t")),
        "holm_p": (e.get("holm") or {}).get("adjusted_p"),
        "n_date_blocks": ((e.get("horizons") or {})
                          .get(str(int(config.CALIB_DECIDING_HORIZON_SESSIONS)),
                               {}).get("spread", {}).get("n_date_blocks")),
        "file": written.get(sid),
    } for sid, e in entries.items()}

    n_cal = sum(1 for v in summary.values() if v["verdict"] == CALIBRATED)
    n_inv = sum(1 for v in summary.values() if v["verdict"] == INVERTED)
    return {
        "job": "C7_signal_calibration",
        "stage": "features",
        "licence": "PRODUCT_EXPERIMENT",
        "roadmap_item": "chunk 22",
        "asof": RUN_DATE,
        "smoke": bool(smoke),
        "inputs": sorted({s for e in entries.values()
                          for s in ((e.get("construction") or {})
                                    .get("panel") or {}).get("sources") or []}
                         | set(uni_block.get("price_source") or [])),
        "family_derived_from": ("recommendation._ADAPTERS x "
                                "signal_registry.permits(id, 'PICKER')"),
        "signals_calibrated": lead,
        "signals_excluded_from_the_family": excluded,
        "resumed": resumed,
        "timed_out": timed_out,
        "holm": hb,
        "summary": summary,
        "outputs": written,
        "headline": (
            f"{len(lead)} leadable signal(s): "
            + ", ".join(f"{sum(1 for v in summary.values() if v['verdict'] == k)} {k}"
                        for k in VERDICTS)),
        "verdict": (CALIBRATED if n_cal else
                    (INVERTED if n_inv else WEAK)),
        "honesty": (
            "Every statistic in every decile table is computed on TEST rows "
            "only, with the cut points refit yearly on the expanding past. "
            "The cost ruler is printed beside every spread and the verdict "
            "reads the NET. A signal with no point-in-time panel on disk is "
            "NO_PANEL naming the table, never a guess. Only CALIBRATED "
            "licenses EXPLOIT capital."),
    }


__all__ = ["CALIBRATED", "INVERTED", "NO_PANEL", "REFUSED", "SCHEMA", "VERDICTS",
           "WEAK", "C7_signal_calibration", "assign_deciles", "attach_forward",
           "build_fusion_panel", "build_insider_panel",
           "build_profitability_panel", "build_universe", "calibrate_signal",
           "decile_table", "family_verdict", "leadable_signals",
           "licensed_bands", "monotonicity", "output_dir", "output_path",
           "run_nulls", "spread_block", "turnover"]
