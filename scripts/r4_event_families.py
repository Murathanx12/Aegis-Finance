"""R4 -- THE EVENT FAMILIES, AND AN HONEST COVERAGE STORY (roadmap block E, item E3).

WHY THIS JOB EXISTS AND WHAT IT REFUSES TO PRETEND
==================================================
`ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` E3 says: run the event books --
PEAD, revision-on-event, surprise x reaction, 8-K item families -- over the
tradable universe through N1's constructions, **gated on E2 >= 90% coverage
per year**.

THAT GATE IS NOT MET FOR THE LEG IT WAS WRITTEN ABOUT, and this job says so
before it computes anything. `BUILD_2026-09-07b_E1_NEWS_PULLER.md` §4 measured
the NEWS corpus at 0.8%-1.2% of the tradable universe for 2015-2024 and
43.7%/46.1% for 2025/2026. It also showed the gate is ambiguous: `month_fraction`
(75-100%) and `universe_fraction` (0.8-46.1%) differ by two orders of magnitude.

A THIRD fact settles the news leg completely, and it is measured here rather
than assumed: **the CRSP daily price panel on disk ends 2024-12-31 and the
graded monthly panel ends 2024-12.** The two years where news coverage is
tolerable (2025, 2026) have NO price panel to grade against, and the ten years
where the price panel exists have ~1% news coverage. So no news-conditioned
event book is gradeable on this tape at all, in either direction. That is a
REFUSAL with a reason, not a null result.

The other three legs are not gated on the news pull and were never measured
against the universe a book is actually built on. This job measures them:

  reading D -- "share of the GRADED PANEL universe with >= 1 event of this
  family in year Y". The panel is what `learner.evaluate.book` selects from, so
  this is the only coverage number that bounds what a book can express.

  IBES quarterly EPS announcements: ~95%-98% of the panel, every year
  1999-2024. The >= 90% gate is MET, on reading D, for the earnings family.

  EDGAR 8-K items: ~13% (2013) -> ~58% (2024), and the corpus's own manifest
  declares two biases that make it a SLICE and not a universe: `survivor_caveat`
  (the CIK list is SEC `company_tickers.json` = CURRENT registrants, so a name
  delisted before the fetch is absent from every earlier year) and
  `coverage_truncation_caveat` (only `filings.recent` was read; median coverage
  start 2016-02-09). Measured here: nearly all of 2015's CIKs are also in 2024's
  set -- the sample is a modern universe replayed backwards.

WHAT IS ACTUALLY RUN, AND UNDER WHAT LABEL
==========================================
  F1  PEAD, MULTIPLE CLOCKS   1 / 5 / 21 / 60 sessions and "to next announcement",
                              each under three return definitions (raw, market
                              excess, pre-event market-model abnormal). The
                              multi-clock design is the point: recent work argues
                              much of the 60-day drift is an expected-return
                              artefact, so one PEAD number would be a claim this
                              job is not entitled to make.
  F2  REVISION-ON-EVENT       the panel's own analyst-revision columns, split by
                              whether an earnings announcement has just landed.
  F3  SURPRISE x REACTION     the expectation-reaction GAP: large |SUE|, small
                              |day-0 reaction|. Information diffusion, not
                              sentiment.
  F4  8-K ITEM FAMILIES       by item number, on the declared SLICE above.
  F5  EARNINGS-SURPRISE HISTORY  up to twelve quarters per company: acceleration,
                              persistence, reversal count, dispersion, magnitude.

THE SHARE-BASIS CHECK, BECAUSE ONE OF THESE RATIOS ALREADY BIT US
=================================================================
`feedback_a_split_adjusted_numerator_over_a_raw_denominator`: IBES `ptgsum`
mixed an adjusted numerator with a raw denominator. Here:
  * `surpsumu` is the UNADJUSTED surprise summary. `actual`, `surpmean` and
    `surpstdev` all come from that one file, so SUE = (actual - surpmean) /
    surpstdev is basis-CONSISTENT by construction and is the primary surprise.
  * The price-scaled surprise divides the same UNADJUSTED `actual - surpmean`
    by CRSP `prc` -- CRSP `prc` is the RAW traded price, the same basis IBES
    unadjusted figures are stated on. `cfacpr` is deliberately NOT applied; the
    adjusted price would be the mismatched denominator.
  Both are reported and the receipt records which is which.

THE RULER
=========
Beta FIRST on every book (2026-09-07 amendment). PRIMARY is the beta-matched
excess. IC, effective breadth, transfer coefficient, hold statistics and typed
exit attribution on every book receipt (invariant 17). `n_effective` counts
DATE BLOCKS -- event MONTHS -- never events (CANON §58): earnings cluster into
four seasons a year and thousands of events share a handful of days.
Family size and FAMILY-MAX p over every cell; BH-FDR for screening, Holm for
export; three eras separately, never pooled; MDE and the power check BEFORE the
confirmation; costs never omitted.

    python -m scripts.r4_event_families --coverage      # stage 1 only
    python -m scripts.r4_event_families --events        # stages 1-2 (no panel books)
    python -m scripts.r4_event_families                 # everything
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP            # noqa: E402
from scripts.labor_a1_shadow_grader import ols_market_model      # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "r4_event_families"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
BULK = WRDS / "bulk"
IBES_SURPSUMU = BULK / "ibes__surpsumu.parquet"
IBES_CRSP_LINK = BULK / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet"
CRSP_STOCKNAMES = BULK / "crsp__stocknames.parquet"
EIGHTK = REPO / "backend" / "data" / "optimus" / "edgar_8k" / "eightk_items.parquet"
EIGHTK_MANIFEST = REPO / "backend" / "data" / "optimus" / "edgar_8k" / "manifest.json"
LONG_PANEL = REPO / "backend" / "data" / "optimus" / "learner" / "train_table_long.parquet"
NEWS_COVERAGE_RECEIPT = Path(
    r"C:\Users\mrthn\aegis-alpha-terminal\state\corpus\corpus_coverage_by_year_2026-09-08.json")
N4_COVERAGE = (REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
               / "N4_coverage_by_year.json")

EVENTS_PARQUET = OUT_DIR / "R4_earnings_events.parquet"
FEATURES_PARQUET = OUT_DIR / "R4_monthly_features.parquet"

#: The window every event study runs on. Bounded ABOVE by the price panel, not
#: by choice: `crsp_dsf_2024.parquet` is the last daily file on disk and
#: `train_table_long.parquet` ends 2024-12.
FIRST_YEAR, LAST_YEAR = 1999, 2024

#: Event-time clocks, in TRADING sessions after the announcement session's
#: close. `next_ann` is the ragged one and is capped so a company that stops
#: reporting cannot contribute a two-year "quarter".
CLOCKS: tuple[int, ...] = (1, 5, 21, 60)
NEXT_ANN_CAP = 120

#: Market-model estimation window, in sessions before the event.
MM_START, MM_END, MM_MIN = -260, -21, 100

NW_LAG = 4
COSTS: tuple[float, ...] = (10.0, 25.0)
DECILES = 10

#: The construction grid, imported in spirit from `scripts/n1_construction_books`
#: (k, weight, hold_k). Row 0 is the incumbent control.
CONSTRUCTIONS: tuple[tuple[int, str, int | None], ...] = (
    (50, "vw", None),
    (100, "ew", 200),
    (300, "ew", 600),
)


# ------------------------------------------------------------------ tiny stats

def _r(v, nd: int = 5):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


def _ncdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _t(series) -> float | None:
    s = pd.Series(series).dropna().astype("float64")
    if len(s) < 3:
        return None
    sd = float(s.std(ddof=1))
    if not math.isfinite(sd) or sd <= 0:
        return None
    return float(s.mean() / (sd / math.sqrt(len(s))))


def _p_two_sided(t: float | None) -> float | None:
    return None if t is None else _r(2.0 * (1.0 - _ncdf(abs(float(t)))), 8)


def _p_one_sided(t: float | None) -> float | None:
    return None if t is None else _r(1.0 - _ncdf(float(t)), 8)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values. EXPORT standard, CANON §63."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None),
                   key=lambda kv: kv[1])
    n, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (n - i) * p))
        out[k] = round(running, 8)
    return out


def bh_fdr(pvals: dict[str, float], q: float = 0.05) -> dict:
    """Benjamini-Hochberg. SCREEN standard, CANON §63."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None),
                   key=lambda kv: kv[1])
    n = len(items)
    if not n:
        return {"n": 0, "q": q, "rejected": [], "adjusted": {}}
    adj, running = {}, 1.0
    for i in range(n - 1, -1, -1):
        k, p = items[i]
        running = min(running, p * n / (i + 1))
        adj[k] = round(min(1.0, running), 8)
    return {"n": n, "q": q,
            "rejected": sorted([k for k, v in adj.items() if v <= q]),
            "adjusted": adj}


def mde_block(series, *, alpha: float = 0.05, power: float = 0.80) -> dict:
    """The two-sided MDE of a paired mean, in the series' own units, and the
    power check -- computed BEFORE any confirmation is quoted (CANON §64).

    `n` is the number of DATE BLOCKS the caller passed, never name-days.
    """
    s = pd.Series(series).dropna().astype("float64")
    n = int(len(s))
    if n < 3:
        return {"verdict": "CANNOT DETERMINE", "n_blocks": n,
                "why": "fewer than 3 date blocks"}
    sd = float(s.std(ddof=1))
    z_a, z_b = 1.959963985, 0.8416212336
    mde = (z_a + z_b) * sd / math.sqrt(n)
    obs = float(s.mean())
    return {
        "n_blocks": n, "alpha": alpha, "power": power,
        "sd_per_block": _r(sd, 6),
        "mde_abs": _r(mde, 6),
        "observed_abs": _r(obs, 6),
        "powered_for_observed_effect": bool(abs(obs) >= mde),
        "blocks_needed_for_observed_effect": (
            int(math.ceil(((z_a + z_b) * sd / abs(obs)) ** 2)) if obs else None),
    }


def _ppf(p: float) -> float:
    from statistics import NormalDist
    return float(NormalDist().inv_cdf(min(max(p, 1e-12), 1.0 - 1e-12)))


def deflated_sharpe(sr_ann: float | None, all_sr_ann, n_periods: int,
                    periods_per_year: int = 12) -> dict:
    """DSR: P(true Sharpe > 0) after deflating for the trials LOOKED AT.

    Bailey & Lopez de Prado (2014). Written to match
    `scripts.strategy_structure_1.deflated_sharpe` term for term -- the
    Gaussian quantile, not a Gumbel one, and the variance taken from the
    FAMILY'S OWN Sharpes rather than a null approximation, because the
    expected maximum depends on how spread the trials actually were.

    `all_sr_ann` is every cell's annualised Sharpe, per invariant 16: every
    cell LOOKED AT, including the ones reported as nothing.
    """
    srs = np.asarray([s for s in np.ravel(all_sr_ann)
                      if s is not None and np.isfinite(s)], dtype="float64")
    if sr_ann is None or n_periods < 8 or srs.size < 2:
        return {"verdict": "CANNOT DETERMINE",
                "why": "no Sharpe, fewer than 8 periods, or fewer than 2 trials"}
    sr_m = float(sr_ann) / math.sqrt(periods_per_year)
    n = int(srs.size)
    v = float(np.var(srs / math.sqrt(periods_per_year), ddof=1))
    gamma = 0.5772156649
    sr0 = math.sqrt(max(v, 0.0)) * ((1.0 - gamma) * _ppf(1 - 1.0 / max(n, 2))
                                    + gamma * _ppf(1 - 1.0 / (max(n, 2) * math.e)))
    z = (sr_m - sr0) * math.sqrt(max(n_periods - 1, 1))
    return {"best_sharpe_ann": _r(sr_ann, 4),
            "n_trials_family": n, "n_periods": int(n_periods),
            "sd_of_trial_sharpes_ann": _r(math.sqrt(max(v, 0.0)) * math.sqrt(periods_per_year), 4),
            "expected_max_sharpe_ann_under_null": _r(sr0 * math.sqrt(periods_per_year), 4),
            "dsr": _r(_ncdf(z), 5),
            "passes_at_0.95": bool(_ncdf(z) > 0.95)}


# --------------------------------------------------------------- the sources

def load_ibes(tracker: RP.InputTracker) -> tuple[pd.DataFrame, dict]:
    """IBES unadjusted quarterly EPS surprises, linked to permno by ICLINK.

    The link is `wrdsapps_link_crsp_ibes__ibcrsphist` -- WRDS's own IBES<->CRSP
    history, with (sdate, edate) intervals -- and the join is INTERVAL, so a
    recycled IBES ticker cannot pick up the wrong company. `score <= 2` keeps
    the two link grades WRDS calls reliable.
    """
    cols = ["ticker", "oftic", "measure", "fiscalp", "usfirm", "anndats",
            "actual", "surpmean", "surpstdev", "suescore"]
    ib = pd.read_parquet(IBES_SURPSUMU, columns=cols)
    tracker.opened(IBES_SURPSUMU)
    n_all = len(ib)
    ib = ib[(ib["measure"] == "EPS") & (ib["fiscalp"] == "QTR")
            & (ib["usfirm"] == 1)].copy()
    n_qtr = len(ib)
    lk = pd.read_parquet(IBES_CRSP_LINK)
    tracker.opened(IBES_CRSP_LINK)
    lk = lk[lk["score"] <= 2][["ticker", "permno", "sdate", "edate"]]
    m = ib.merge(lk, on="ticker", how="left")
    m = m[(m["anndats"] >= m["sdate"]) & (m["anndats"] <= m["edate"])]
    m = m.drop_duplicates(["permno", "anndats"], keep="first")
    m["permno"] = m["permno"].astype("int64")
    m["year"] = m["anndats"].dt.year
    # The NEXT announcement is computed on the WHOLE tape, before any cohort
    # slice: computing it inside a cohort would hand the last event of every
    # five-year block a missing successor and quietly shorten one clock.
    m = m.sort_values(["permno", "anndats"], kind="mergesort").reset_index(drop=True)
    m["next_anndats"] = m.groupby("permno")["anndats"].shift(-1)
    note = {
        "file": str(IBES_SURPSUMU),
        "rows_in_file": int(n_all),
        "rows_us_quarterly_eps": int(n_qtr),
        "rows_linked_to_permno": int(len(m)),
        "link_share": _r(len(m) / max(n_qtr, 1), 4),
        "link": "wrdsapps_link_crsp_ibes__ibcrsphist, score<=2, INTERVAL join on anndats",
        "share_basis": ("surpsumu is the UNADJUSTED summary; actual, surpmean and "
                        "surpstdev are all from that one file, so SUE is "
                        "basis-consistent. The price-scaled surprise divides the "
                        "same unadjusted numerator by CRSP RAW prc (cfacpr NOT "
                        "applied) -- the matching basis."),
        "pit": ("anndats is both the event and its availability (the actual EPS IS "
                "the announcement). DATE precision only: IBES surpsumu carries no "
                "time of day, so entry is the announcement session's CLOSE and "
                "every clock starts at +1."),
    }
    return m, note


def load_eightk(tracker: RP.InputTracker) -> tuple[pd.DataFrame, dict]:
    """EDGAR 8-K item codes, linked to permno. A DECLARED SLICE, not a universe."""
    d = pd.read_parquet(EIGHTK, columns=["ticker", "permno", "cik", "event_date",
                                         "filing_date", "acceptance_datetime",
                                         "items_joined"])
    tracker.opened(EIGHTK)
    d["ticker"] = d["ticker"].astype("string").str.upper().str.strip()
    acc = pd.to_datetime(d["acceptance_datetime"], errors="coerce", utc=True)
    d["observed_at"] = acc.dt.tz_localize(None).fillna(
        pd.to_datetime(d["filing_date"], errors="coerce"))
    sn = pd.read_parquet(CRSP_STOCKNAMES,
                         columns=["permno", "namedt", "nameenddt", "shrcd",
                                  "exchcd", "ticker"])
    tracker.opened(CRSP_STOCKNAMES)
    sn = sn[sn["shrcd"].isin([10, 11]) & sn["exchcd"].isin([1, 2, 3])]
    sn["ticker"] = sn["ticker"].astype("string").str.upper().str.strip()
    sn = sn.dropna(subset=["ticker"])[["ticker", "permno", "namedt", "nameenddt"]]
    sn = sn.rename(columns={"permno": "permno_sn"})
    mm = d.merge(sn, on="ticker", how="left")
    mm = mm[(mm["observed_at"] >= mm["namedt"]) & (mm["observed_at"] <= mm["nameenddt"])]
    mm["permno"] = mm["permno"].fillna(mm["permno_sn"]).astype("int64")
    mm = mm.drop_duplicates(["permno", "observed_at", "items_joined"], keep="first")
    mm["year"] = mm["observed_at"].dt.year
    man = json.loads(EIGHTK_MANIFEST.read_text(encoding="utf-8"))
    yy = pd.to_datetime(d["filing_date"], errors="coerce").dt.year
    ciks = {int(y): set(g) for y, g in d["cik"].groupby(yy)}
    a, b = ciks.get(2015, set()), ciks.get(2024, set())
    note = {
        "file": str(EIGHTK),
        "rows_in_file": int(len(d)),
        "rows_linked_to_permno": int(len(mm)),
        "link": ("crsp__stocknames INTERVAL join on the acceptance timestamp, "
                 "shrcd 10/11, exchcd 1/2/3"),
        "pit": "observed_at = EDGAR acceptance_datetime; event_date is NEVER the gate",
        "DECLARED_BIASES": {
            "survivorship": man.get("survivor_caveat"),
            "truncation": man.get("coverage_truncation_caveat"),
            "coverage_start_median": man.get("coverage_start_median"),
            "measured_here": (
                f"{len(a & b)} of {len(a)} CIKs filing in 2015 also file in 2024 "
                f"-- the CIK list is a MODERN universe replayed backwards, so a "
                f"name delisted before the collector ran is absent from every "
                f"earlier year. Direction of the bias: toward survivors, i.e. "
                f"UPWARD on any return computed from it."),
        },
        "verdict": ("SLICE -- gradeable as a conditional event study inside the "
                    "surviving set, NOT as a book over a universe."),
    }
    return mm, note


def _dsf_path(year: int) -> Path:
    return WRDS / f"crsp_dsf_{year}.parquet"


def load_daily(years: list[int], tracker: RP.InputTracker) -> pd.DataFrame:
    """CRSP daily returns for `years`, long form, float32."""
    frames = []
    for y in years:
        p = _dsf_path(y)
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["permno", "date", "ret", "prc"])
        tracker.opened(p)
        d = d[np.isfinite(d["ret"].to_numpy(dtype="float64"))]
        d["permno"] = d["permno"].astype("int32")
        d["ret"] = d["ret"].astype("float32")
        d["prc"] = d["prc"].astype("float32")
        frames.append(d)
    if not frames:
        return pd.DataFrame(columns=["permno", "date", "ret", "prc"])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


def price_panel_bound() -> dict:
    """WHERE THE TAPE STOPS. Derived from the files, never asserted."""
    years = sorted(int(p.stem.split("_")[-1]) for p in WRDS.glob("crsp_dsf_*.parquet"))
    return {"crsp_daily_years_on_disk": [years[0], years[-1]] if years else None,
            "n_year_files": len(years),
            "note": ("no daily file after "
                     f"{years[-1] if years else '?'} -- every event clock is "
                     "bounded above by it, and no amount of news coverage in "
                     "2025-2026 can be graded without one")}


# --------------------------------------------------------------- stage 1

def stage1_coverage(ib: pd.DataFrame, ek: pd.DataFrame,
                    tracker: RP.InputTracker) -> dict:
    """THE COVERAGE STATEMENT. Four readings, each named, none averaged."""
    pan = pd.read_parquet(LONG_PANEL, columns=["permno", "month"])
    tracker.opened(LONG_PANEL)
    pan["year"] = pan["month"].str[:4].astype(int)
    pan_ids = {int(y): set(g.astype(int)) for y, g in pan["permno"].groupby(pan["year"])}
    ib_ids = {int(y): set(g.astype(int)) for y, g in ib["permno"].groupby(ib["year"])}
    ek_ids = {int(y): set(g.astype(int)) for y, g in ek["permno"].groupby(ek["year"])}

    rows = {}
    for y in range(FIRST_YEAR, LAST_YEAR + 1):
        P = pan_ids.get(y, set())
        rows[str(y)] = {
            "panel_names": len(P),
            "ibes_earnings_names_in_panel": len(P & ib_ids.get(y, set())),
            "ibes_earnings_share_of_panel": _r(len(P & ib_ids.get(y, set())) / max(len(P), 1), 4),
            "eightk_names_in_panel": len(P & ek_ids.get(y, set())),
            "eightk_share_of_panel": _r(len(P & ek_ids.get(y, set())) / max(len(P), 1), 4),
        }
    ib_shares = [v["ibes_earnings_share_of_panel"] for v in rows.values()]
    ek_shares = [v["eightk_share_of_panel"] for v in rows.values() if v["eightk_names_in_panel"]]

    news = {"status": "ABSENT", "path": str(NEWS_COVERAGE_RECEIPT)}
    if NEWS_COVERAGE_RECEIPT.exists():
        try:
            raw = json.loads(NEWS_COVERAGE_RECEIPT.read_text(encoding="utf-8"))
            tracker.opened(NEWS_COVERAGE_RECEIPT)
            news = {"status": "read", "path": str(NEWS_COVERAGE_RECEIPT),
                    "by_year": raw.get("by_year", raw)}
        except Exception as exc:                                    # noqa: BLE001
            news = {"status": "REFUSED", "why": f"{type(exc).__name__}: {exc}"}

    n4 = {"status": "ABSENT", "path": str(N4_COVERAGE)}
    if N4_COVERAGE.exists():
        raw = json.loads(N4_COVERAGE.read_text(encoding="utf-8"))
        tracker.opened(N4_COVERAGE)
        n4 = {"status": "read",
              "share_of_crsp_common_stock_by_year": {
                  y: v.get("share_of_universe_proxy_covered")
                  for y, v in raw.get("by_year", {}).items()}}

    return {
        "WHICH_READING_EVERY_NUMBER_IS_CONDITIONED_ON": {
            "A_month_fraction": ("months of the year with any NEWS row. A "
                                 "PIPELINE-HEALTH number. 75%-100%. It is what "
                                 "caught the 03:18 death and it says nothing "
                                 "about how many companies are covered."),
            "B_news_universe_fraction": ("distinct NEWS symbols with >=1 row that "
                                         "year / the 12,198-name tradable universe. "
                                         "0.8%-1.2% for 2015-2024, 43.7%/46.1% for "
                                         "2025/2026. Terminal receipt, not re-derived."),
            "C_event_table_permno_share": ("N4's reading: linked permnos in the "
                                           "event table / CRSP common stock active "
                                           "that year, ALL sources pooled. 80.8%-86.3% "
                                           "for 2015-2024. It is dominated by IBES and "
                                           "8-K, so it is NOT a news number and reading "
                                           "it as one is the error this table exists to "
                                           "stop."),
            "D_panel_share_THIS_JOB": ("names in the GRADED MONTHLY PANEL with >=1 "
                                       "event of THIS family in year Y / all panel "
                                       "names that year. The panel is what "
                                       "`evaluate.book` selects from, so D is the "
                                       "only reading that bounds what a book can "
                                       "express. Every family number below is "
                                       "conditioned on D."),
        },
        "reading_D_by_year": rows,
        "reading_D_summary": {
            "ibes_earnings_min_share": _r(min(ib_shares), 4),
            "ibes_earnings_max_share": _r(max(ib_shares), 4),
            "ibes_earnings_gate_90pct": "MET in every year 1999-2024",
            "eightk_min_share": _r(min(ek_shares), 4) if ek_shares else None,
            "eightk_max_share": _r(max(ek_shares), 4) if ek_shares else None,
            "eightk_gate_90pct": "NOT MET in any year -- and the sample is survivor-conditioned",
        },
        "reading_B_news_terminal_receipt": news,
        "reading_C_event_table": n4,
        "price_panel_bound": price_panel_bound(),
        "graded_panel_bound": {
            "first_month": str(pan["month"].min()), "last_month": str(pan["month"].max()),
            "note": ("the monthly panel `evaluate.book` selects from. It ends the "
                     "same month the daily files do."),
        },
        "THE_NEWS_LEG_IS_REFUSED": {
            "verdict": "REFUSED -- not a null result",
            "why": ("2015-2024 has a price panel and ~1% news coverage of the "
                    "tradable universe; 2025-2026 has 43.7%/46.1% news coverage "
                    "and NO price panel (CRSP daily ends 2024-12-31, the monthly "
                    "panel ends 2024-12). There is no year in which a "
                    "news-conditioned event book can be both built and graded. "
                    "This is a property of the tape, not of the hypothesis."),
            "what_would_lift_it": ("either the 2015-2024 whole-market Alpaca pull "
                                   "(~50 h, resumable, command in "
                                   "BUILD_2026-09-07b_E1_NEWS_PULLER.md §8) or a "
                                   "2025-2026 daily price file. The pull is the "
                                   "cheaper of the two."),
        },
        "months_excluded_and_why": {
            "degraded_news_months": ["alpaca 2025-01", "alpaca 2025-03",
                                     "finnhub 2025-02", "finnhub 2026-01"],
            "why": ("DONE but NOT FULL -- a 17-hour DNS outage on 2026-09-07/08. "
                    "`--list-degraded` in the terminal repo names them. They are "
                    "NOT averaged over here because the news leg is refused "
                    "outright, so no number in this document depends on them."),
            "eightk_years_excluded": ("2013-2016 are reported but never traded: the "
                                      "manifest's median coverage_start is 2016-02-09, "
                                      "so an absence before it is truncation, not a "
                                      "company that filed nothing."),
        },
    }


# ------------------------------------------------- stage 2: the event tape

def build_event_tape(ib: pd.DataFrame, daily: pd.DataFrame,
                     lo_year: int = FIRST_YEAR,
                     hi_year: int = LAST_YEAR,
                     pseudo_offset: int = 0) -> tuple[pd.DataFrame, dict]:
    """One row per (permno, announcement) with every clock's return already on it.

    TWO ENTRY CONVENTIONS, AND WHY BOTH ARE CARRIED.
    IBES `surpsumu` carries no announcement TIME OF DAY, only `anndats`. A large
    minority of US companies report AFTER the close. So:

      * entry `e1` -- the close of session 0 (the session on or after `anndats`).
        This is `event_response_v1`'s convention. It is right for a company that
        reported intraday and it is a LOOKAHEAD for one that reported after the
        bell, because the close of session 0 is before the announcement.
      * entry `e2` -- the close of session +1. PIT-SAFE for BOTH timings, at the
        cost of giving away one session of drift.

    `e2` is the PRIMARY. `e1` is reported beside it, and the gap between them is
    itself the answer to "how much of PEAD is the first session?". Reporting
    only `e1` would be the same defect as trading a pre-open signal on the
    previous close.

    The REACTION is session 0 and session +1 compounded (`reaction_01`), for the
    same reason: whichever session carried the announcement, it is inside it.
    """
    daily = daily.sort_values(["permno", "date"], kind="mergesort")
    dates = np.sort(daily["date"].unique())
    d_idx = pd.Series(np.arange(len(dates)), index=pd.DatetimeIndex(dates))

    # EW market return per session, over every CRSP common name trading that day.
    mkt = daily.groupby("date")["ret"].mean().astype("float64")
    mkt_arr = mkt.reindex(pd.DatetimeIndex(dates)).to_numpy(dtype="float64")

    # per-permno contiguous blocks in the sorted frame
    pn = daily["permno"].to_numpy()
    starts = np.flatnonzero(np.r_[True, pn[1:] != pn[:-1]])
    ends = np.r_[starts[1:], len(pn)]
    blocks = {int(pn[s]): (int(s), int(e)) for s, e in zip(starts, ends)}
    ret_all = daily["ret"].to_numpy(dtype="float64")
    prc_all = daily["prc"].to_numpy(dtype="float64")
    di_all = d_idx.reindex(pd.DatetimeIndex(daily["date"])).to_numpy()

    ev = ib[(ib["year"] >= lo_year) & (ib["year"] <= hi_year)].copy()
    ev = ev.sort_values(["permno", "anndats"], kind="mergesort").reset_index(drop=True)

    out_rows: list[dict] = []
    skipped = {"no_price_block": 0, "no_session_on_or_after": 0, "short_forward": 0}

    for permno, g in ev.groupby("permno", sort=False):
        blk = blocks.get(int(permno))
        if blk is None:
            skipped["no_price_block"] += len(g)
            continue
        s, e = blk
        di = di_all[s:e]                 # global session index of each row
        r = ret_all[s:e]
        pr = prc_all[s:e]
        for rec in g.itertuples(index=False):
            ann = rec.anndats
            gi = d_idx.get(ann, None)
            if gi is None:
                # announcement fell on a non-session -- take the next session
                pos = int(np.searchsorted(dates, np.datetime64(ann), side="left"))
                if pos >= len(dates):
                    skipped["no_session_on_or_after"] += 1
                    continue
                gi = pos
            j = int(np.searchsorted(di, gi, side="left"))
            if pseudo_offset:
                # THE PLACEBO DATE. Everything downstream is identical; only
                # session 0 moves. It answers the one question a "the reaction
                # predicts" result cannot dodge: is it the EVENT that makes a
                # two-session move informative, or would any two-session move
                # in the same name and the same month do as well?
                j += int(pseudo_offset)
                if j >= len(di):
                    skipped["no_session_on_or_after"] += 1
                    continue
                gi = int(di[j])
            if j >= len(di) or di[j] != gi:
                # the name did not trade that session; use its next session
                if j >= len(di):
                    skipped["no_session_on_or_after"] += 1
                    continue
            row = {
                "permno": int(permno),
                # on a placebo run the tape is dated by the PLACEBO session, so
                # `event_month` blocks contemporaneous placebo events together
                # and the within-month ranks compare like with like
                "anndats": (pd.Timestamp(dates[gi]) if pseudo_offset else ann),
                "true_anndats": ann,
                "year": int(rec.year),
                "actual": rec.actual, "surpmean": rec.surpmean,
                "surpstdev": rec.surpstdev, "suescore": rec.suescore,
            }
            row["prc_raw_day0"] = float(abs(pr[j])) if np.isfinite(pr[j]) else np.nan
            row["reaction_day0"] = float(r[j])
            row["reaction_day1"] = float(r[j + 1]) if j + 1 < len(r) else np.nan
            row["reaction_01"] = (
                float((1.0 + r[j]) * (1.0 + r[j + 1]) - 1.0) if j + 1 < len(r)
                else float(r[j]))
            row["mm_alpha"] = np.nan
            row["mm_beta"] = np.nan
            # ---- pre-event market model on the name's OWN sessions
            lo = j + MM_START
            hi = j + MM_END
            if lo >= 0 and hi > lo:
                yy = r[lo:hi]
                xx = mkt_arr[di[lo:hi]]
                ok = np.isfinite(yy) & np.isfinite(xx)
                if int(ok.sum()) >= MM_MIN and float(np.var(xx[ok])) > 0:
                    b = float(np.cov(yy[ok], xx[ok], ddof=1)[0, 1] / np.var(xx[ok], ddof=1))
                    a = float(yy[ok].mean() - b * xx[ok].mean())
                    row["mm_alpha"], row["mm_beta"] = a, b
            # ---- forward clocks
            nxt = rec.next_anndats
            n_next = NEXT_ANN_CAP
            if pd.notna(nxt):
                pos2 = int(np.searchsorted(dates, np.datetime64(nxt), side="left"))
                n_next = max(1, min(NEXT_ANN_CAP, pos2 - int(gi)))
            for entry in (1, 2):
                for tag, h in (list(zip([str(c) for c in CLOCKS], CLOCKS))
                               + [("next_ann", max(1, n_next - entry + 1))]):
                    keys = [f"car_{b}_{tag}_e{entry}" for b in ("raw", "mkt", "ab", "bo")]
                    a0, a1 = j + entry, j + entry + h
                    if a1 > len(r) or a0 >= len(r):
                        for k in keys:
                            row[k] = np.nan
                        continue
                    rr = r[a0:a1]
                    mm = mkt_arr[di[a0:a1]]
                    ok = np.isfinite(rr) & np.isfinite(mm)
                    if ok.sum() < max(1, int(0.6 * h)):
                        for k in keys:
                            row[k] = np.nan
                        continue
                    raw = float(np.prod(1.0 + rr[ok]) - 1.0)
                    mkr = float(np.prod(1.0 + mm[ok]) - 1.0)
                    row[keys[0]] = raw
                    row[keys[1]] = raw - mkr
                    if np.isfinite(row["mm_beta"]):
                        # `ab` subtracts the FULL fitted pre-event expectation,
                        # alpha included. `bo` subtracts the BETA term only.
                        # The two must be reported side by side: over 60
                        # sessions the alpha term compounds, and a high-SUE
                        # name's fitted alpha contains its own pre-announcement
                        # run-up, so `ab` alone would charge the drift for
                        # momentum that the announcement did not cause.
                        row[keys[2]] = raw - float(np.prod(
                            1.0 + row["mm_alpha"] + row["mm_beta"] * mm[ok]) - 1.0)
                        row[keys[3]] = raw - float(np.prod(
                            1.0 + row["mm_beta"] * mm[ok]) - 1.0)
                    else:
                        row[keys[2]] = np.nan
                        row[keys[3]] = np.nan
            row["h_next_ann"] = int(n_next)
            out_rows.append(row)

    tape = pd.DataFrame(out_rows)
    if tape.empty:
        return tape, {"status": "REFUSED", "why": "no event matched a price block"}

    # ---- the two surprises, both basis-checked
    sd = tape["surpstdev"].replace(0.0, np.nan)
    tape["sue"] = (tape["actual"] - tape["surpmean"]) / sd
    tape["sue_ibes"] = tape["suescore"]
    tape["sue_price"] = ((tape["actual"] - tape["surpmean"])
                         / tape["prc_raw_day0"].replace(0.0, np.nan))
    tape["event_month"] = tape["anndats"].dt.to_period("M").astype(str)
    note = {
        "events": int(len(tape)),
        "first": str(tape["anndats"].min().date()), "last": str(tape["anndats"].max().date()),
        "event_months_date_blocks": int(tape["event_month"].nunique()),
        "skipped": skipped,
        "market_model": {"window_sessions": [MM_START, MM_END], "min_sessions": MM_MIN,
                         "fitted_share": _r(float(tape["mm_beta"].notna().mean()), 4),
                         "market": "EW CRSP common-stock daily return"},
        "clocks": {str(c): "sessions held, starting at the entry session" for c in CLOCKS}
                  | {"next_ann": f"to the NEXT announcement, capped at {NEXT_ANN_CAP} sessions"},
        "entry": {
            "e2_PRIMARY": ("enter at the close of session +1 -- PIT-safe whether the "
                           "company reported intraday or after the bell"),
            "e1_SECONDARY": ("enter at the close of session 0 -- `event_response_v1`'s "
                             "convention; a LOOKAHEAD for an after-close reporter, and "
                             "carried only so the one-session gap is visible"),
            "reaction": "reaction_01 = sessions 0 and +1 compounded",
        },
        "return_bases": {
            "raw": "the name's own compounded return over the window",
            "mkt": "raw minus the EW market compounded over the same sessions",
            "bo": ("raw minus BETA x market -- the pre-event market-model beta only, "
                   "no alpha term. The clean expected-return decomposition."),
            "ab": ("raw minus (alpha + beta x market) -- the FULL fitted pre-event "
                   "expectation. Over a long clock the alpha term compounds and it "
                   "carries the name's own pre-announcement run-up, so `ab` is a "
                   "momentum-charged upper bound on the correction, not the "
                   "correction. Read `bo` and `ab` together or neither."),
        },
        "sue_definitions": {
            "sue": "(actual - surpmean) / surpstdev, all three from surpsumu (UNADJUSTED) -- PRIMARY",
            "sue_ibes": "IBES's own suescore column, carried for cross-check",
            "sue_price": ("(actual - surpmean) / |CRSP raw prc| on day 0. cfacpr is "
                          "NOT applied: an unadjusted numerator needs an unadjusted "
                          "denominator (feedback_a_split_adjusted_numerator_over_a_raw_denominator)"),
        },
    }
    return tape, note


def build_event_tape_all(ib: pd.DataFrame, tracker: RP.InputTracker,
                         log=print, pseudo_offset: int = 0
                         ) -> tuple[pd.DataFrame, dict]:
    """The whole 1999-2024 tape, in five-year cohorts.

    MEMORY, DECLARED. The full 1997-2024 daily file is ~33.6M rows and about
    1.2 GB once pandas is done with it; this box had 6.5 GB free with two news
    pullers and several other agents' jobs on it. Cohorts of five event-years
    with a two-year lookback (the market-model window is 260 sessions) and a
    one-year lookahead hold ~9M rows, ~350 MB, and the tape is concatenated at
    the end. Nothing here loads the long panel.
    """
    tapes, notes = [], {}
    for lo in range(FIRST_YEAR, LAST_YEAR + 1, 5):
        hi = min(lo + 4, LAST_YEAR)
        yrs = [y for y in range(lo - 2, hi + 2) if _dsf_path(y).exists()]
        t0 = time.perf_counter()
        d = load_daily(yrs, tracker)
        tape, note = build_event_tape(ib, d, lo, hi, pseudo_offset=pseudo_offset)
        del d
        gc.collect()
        if not tape.empty:
            tapes.append(tape)
        note["daily_years_loaded"] = [yrs[0], yrs[-1]] if yrs else None
        note["elapsed_s"] = _r(time.perf_counter() - t0, 1)
        notes[f"{lo}-{hi}"] = note
        log(f"    cohort {lo}-{hi}: {len(tape):,} events, {note['elapsed_s']}s")
    if not tapes:
        return pd.DataFrame(), {"status": "REFUSED", "why": "no cohort produced events"}
    out = pd.concat(tapes, ignore_index=True)
    roll = {
        "events_total": int(len(out)),
        "event_months_date_blocks": int(out["event_month"].nunique()),
        "distinct_permnos": int(out["permno"].nunique()),
        "first": str(out["anndats"].min().date()), "last": str(out["anndats"].max().date()),
        "market_model_fitted_share": _r(float(out["mm_beta"].notna().mean()), 4),
        "cohorts": notes,
    }
    return out, roll


# ------------------------------------ stage 3: PEAD on multiple clocks

def _decile(s: pd.Series) -> pd.Series:
    """Within-group decile, 0..9. RANK-based, so the SUE outliers that
    `surpstdev` near zero manufactures cannot move a bucket edge."""
    r = s.rank(method="first", pct=True)
    return np.minimum((r * DECILES).astype("float64"), DECILES - 1e-9).astype(int)


def _monthly_spread(tape: pd.DataFrame, sig: str, ret: str) -> pd.Series:
    """One number per EVENT MONTH: mean(top decile) - mean(bottom decile).

    CANON §58. Earnings cluster into four seasons; pooling events would count
    thousands of name-days that share a handful of market days as independent.
    The spread is formed WITHIN the month, so the month's own market move
    cancels out of it before any t is taken.
    """
    d = tape[["event_month", sig, ret]].dropna()
    if d.empty:
        return pd.Series(dtype="float64")
    out = {}
    for m, g in d.groupby("event_month", sort=True):
        if len(g) < 40:
            continue
        dec = _decile(g[sig])
        hi = g.loc[dec == DECILES - 1, ret]
        lo = g.loc[dec == 0, ret]
        if len(hi) < 3 or len(lo) < 3:
            continue
        out[m] = float(hi.mean() - lo.mean())
    return pd.Series(out, dtype="float64").sort_index()


def _era_of(month: str) -> str:
    y = int(str(month)[:4])
    if y <= 2007:
        return "1999-2007"
    if y <= 2015:
        return "2008-2015"
    return "2016-2024"


def era_table(s: pd.Series) -> dict:
    """The three canonical `learner.long_panel` eras, SEPARATELY. Never pooled."""
    s = pd.Series(s).dropna()
    out, signs = {}, []
    for era in ("1999-2007", "2008-2015", "2016-2024"):
        g = s[[_era_of(m) == era for m in s.index]]
        if len(g) < 6:
            out[era] = {"blocks": int(len(g)), "mean_pct": None, "t": None,
                        "note": "fewer than 6 date blocks"}
            continue
        t = _t(g)
        out[era] = {"blocks": int(len(g)), "mean_pct": _r(float(g.mean()) * 100, 4),
                    "t": _r(t, 3), "sign": int(np.sign(g.mean()))}
        signs.append(int(np.sign(g.mean())))
    out["eras_measured"] = len(signs)
    out["eras_same_sign_as_full"] = (
        sum(1 for x in signs if x == int(np.sign(s.mean()))) if len(s) else 0)
    return out


def cell(tape: pd.DataFrame, sig: str, ret: str, *, label: str) -> dict:
    """One family cell: the monthly decile spread, its t, its eras, its MDE.

    `beta_of_the_spread` is printed FIRST because a long-short decile spread is
    NOT automatically market-neutral: if the high-SUE decile is systematically
    higher-beta than the low-SUE decile, part of the spread is the market.
    """
    s = _monthly_spread(tape, sig, ret)
    if len(s) < 8:
        return {"label": label, "verdict": "CANNOT DETERMINE",
                "date_blocks": int(len(s)), "why": "fewer than 8 event months"}
    # beta of the spread on the same months' market move
    beta_blk = {}
    d = tape[["event_month", sig, "mm_beta", "mm_alpha"]].dropna()
    if not d.empty:
        bs, als = {}, {}
        for m, g in d.groupby("event_month", sort=True):
            if len(g) < 40:
                continue
            dec = _decile(g[sig])
            top, bot = dec == DECILES - 1, dec == 0
            if int(top.sum()) < 3 or int(bot.sum()) < 3:
                continue
            bs[m] = float(g.loc[top, "mm_beta"].mean() - g.loc[bot, "mm_beta"].mean())
            als[m] = float(g.loc[top, "mm_alpha"].mean() - g.loc[bot, "mm_alpha"].mean())
        bser = pd.Series(bs, dtype="float64")
        aser = pd.Series(als, dtype="float64")
        beta_blk = {
            "mean_pre_event_beta_top_minus_bottom": _r(float(bser.mean()), 4),
            "mean_pre_event_DAILY_alpha_top_minus_bottom": _r(float(aser.mean()), 7),
            "that_alpha_differential_over_60_sessions_pct": _r(
                float(aser.mean()) * 60 * 100, 4),
            "note": ("pre-event market-model betas and alphas of the two extreme "
                     "deciles. On `raw` and `mkt` neither is removed. On `bo` the "
                     "BETA is removed and the alpha is not. On `ab` both are, and "
                     "the alpha row above is the size of what `ab` takes off a "
                     "60-session clock -- read it before reading `ab`."),
        }
    t = _t(s)
    return {
        "label": label,
        "BETA_FIRST": beta_blk,
        "date_blocks_n_effective": int(len(s)),
        "events_used": int(tape[[sig, ret]].dropna().shape[0]),
        "mean_spread_pct_per_event": _r(float(s.mean()) * 100, 4),
        "median_spread_pct": _r(float(s.median()) * 100, 4),
        "t_on_date_blocks": _r(t, 3),
        "p_two_sided": _p_two_sided(t),
        "share_of_blocks_positive": _r(float((s > 0).mean()), 4),
        "mde_and_power": mde_block(s),
        "eras": era_table(s),
        "_series": s,
    }


# ---------------------------------- stage 4: the derived surprise features

def attach_surprise_features(tape: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """F3 (surprise x reaction) and F5 (earnings history), on the event tape.

    EVERY FEATURE IS CROSS-SECTIONALLY RANKED WITHIN ITS EVENT MONTH FIRST.
    `surpstdev` can be near zero, which manufactures a SUE of -3,476 out of a
    penny; a raw SUE is therefore unusable as a level and every level-based
    statistic below (mean, dispersion, trend) is computed on the RANK, which is
    bounded in [-0.5, 0.5] by construction and cannot be moved by one estimate
    that happened to agree.
    """
    t = tape.sort_values(["permno", "anndats"], kind="mergesort").reset_index(drop=True)
    g_m = t.groupby("event_month")

    t["sue_pct"] = g_m["sue"].rank(pct=True) - 0.5
    t["reac_pct"] = g_m["reaction_01"].rank(pct=True) - 0.5
    t["sue_abs_pct"] = g_m["sue"].transform(lambda s: s.abs().rank(pct=True))
    t["reac_abs_pct"] = g_m["reaction_01"].transform(lambda s: s.abs().rank(pct=True))

    # F3 -- THE EXPECTATION-REACTION GAP.
    # Positive = the fundamental surprise was ranked far higher than the price
    # response to it. That is the diffusion cell, and it is a DIFFERENT object
    # from "the surprise was positive".
    t["gap"] = t["sue_pct"] - t["reac_pct"]
    #: the named cell the mandate asks for: LARGE |surprise|, SMALL |reaction|
    t["cell_big_surprise_small_reaction"] = (
        (t["sue_abs_pct"] >= 0.8) & (t["reac_abs_pct"] <= 0.2)).astype("int8")
    #: the signed return an operator would actually earn in that cell
    t["signed_sue"] = np.sign(t["sue_pct"])

    # F5 -- EARNINGS-SURPRISE HISTORY, up to twelve quarters, PAST ONLY.
    # `shift(1)` before every rolling window: the trajectory a decision at
    # announcement t may use is t-1 back, PLUS t itself where stated. Features
    # that would need t+1 do not exist here.
    gp = t.groupby("permno")["sue_pct"]
    prev = gp.shift(1)
    t["sue_prev"] = prev
    t["hist_accel"] = t["sue_pct"] - prev
    t["hist_mean_8"] = gp.transform(lambda s: s.rolling(8, min_periods=4).mean())
    t["hist_sd_8"] = gp.transform(lambda s: s.rolling(8, min_periods=4).std())
    t["hist_mag_8"] = gp.transform(lambda s: s.abs().rolling(8, min_periods=4).mean())
    t["hist_mean_12"] = gp.transform(lambda s: s.rolling(12, min_periods=6).mean())

    sgn = np.sign(t["sue_pct"]).replace(0, np.nan)
    t["_sgn"] = sgn
    flip = (sgn != t.groupby("permno")["_sgn"].shift(1)).astype("float64")
    flip[t.groupby("permno")["_sgn"].shift(1).isna()] = np.nan
    t["_flip"] = flip
    t["hist_reversals_8"] = t.groupby("permno")["_flip"].transform(
        lambda s: s.rolling(8, min_periods=4).sum())

    def _streak(s: pd.Series) -> pd.Series:
        out, run, last = [], 0, 0.0
        for v in s.to_numpy():
            if not np.isfinite(v) or v == 0:
                run = 0
            elif v == last:
                run += 1
            else:
                run = 1
            last = v if np.isfinite(v) else last
            out.append(run * (1 if last > 0 else -1))
        return pd.Series(out, index=s.index, dtype="float64")

    t["hist_persistence"] = t.groupby("permno")["_sgn"].transform(_streak)

    def _slope(s: pd.Series) -> float:
        v = s.dropna().to_numpy()
        if len(v) < 4:
            return np.nan
        x = np.arange(len(v), dtype="float64")
        return float(np.polyfit(x, v, 1)[0])

    t["hist_trend_8"] = t.groupby("permno")["sue_pct"].transform(
        lambda s: s.rolling(8, min_periods=4).apply(_slope, raw=False))
    t = t.drop(columns=["_sgn", "_flip"])

    note = {
        "features": {
            "sue_pct": "within-event-month percentile rank of SUE, centred (-0.5..0.5)",
            "reac_pct": "same, of the 0/+1 compounded reaction",
            "gap": ("sue_pct - reac_pct. THE EXPECTATION-REACTION GAP: how much "
                    "more the fundamentals surprised than the price responded."),
            "cell_big_surprise_small_reaction": "|SUE| in the top quintile AND |reaction| in the bottom quintile",
            "hist_accel": "sue_pct(t) - sue_pct(t-1)",
            "hist_mean_8 / hist_mean_12": "trailing mean of sue_pct over 8 / 12 quarters",
            "hist_sd_8": "trailing dispersion",
            "hist_mag_8": "trailing mean |sue_pct| -- magnitude, sign-free",
            "hist_reversals_8": "sign flips of sue_pct in the trailing 8",
            "hist_persistence": "signed run length of same-sign surprises ending at t",
            "hist_trend_8": "OLS slope of sue_pct on quarter index over the trailing 8",
        },
        "pit": ("every trailing window ends at the CURRENT announcement, which is "
                "public at the entry the clocks use. `hist_accel` uses t-1. No "
                "feature reads a later quarter."),
        "coverage": {c: _r(float(t[c].notna().mean()), 4) for c in
                     ("sue_pct", "gap", "hist_accel", "hist_mean_8", "hist_sd_8",
                      "hist_mag_8", "hist_reversals_8", "hist_persistence",
                      "hist_trend_8")},
        "cell_share": _r(float(t["cell_big_surprise_small_reaction"].mean()), 4),
    }
    return t, note


# --------------------------------- stage 5: 8-K item families (a SLICE)

def eightk_families(ek: pd.DataFrame, tracker: RP.InputTracker,
                    log=print) -> tuple[dict, dict]:
    """CAR after each 8-K ITEM code, on the declared survivor-conditioned slice.

    THE CONTROL IS THE OTHER 8-K FILINGS, NOT THE MARKET. Every row here comes
    from the same survivor-conditioned CIK list, so an item's CAR measured
    against the market would be reporting the sample's survivorship. Measured
    against the mean CAR of all OTHER 8-K filings in the same event month, the
    bias is differenced out of the comparison -- which is the only question an
    item family can honestly answer on this tape: *does THIS item behave
    differently from an average 8-K?*
    """
    ek = ek[(ek["year"] >= 2017) & (ek["year"] <= LAST_YEAR)].copy()
    ek["event_month"] = ek["observed_at"].dt.to_period("M").astype(str)
    rows = []
    for lo in range(2017, LAST_YEAR + 1, 4):
        hi = min(lo + 3, LAST_YEAR)
        yrs = [y for y in range(lo, hi + 2) if _dsf_path(y).exists()]
        d = load_daily(yrs, tracker)
        if d.empty:
            continue
        d = d.sort_values(["permno", "date"], kind="mergesort")
        dates = np.sort(d["date"].unique())
        d_idx = pd.Series(np.arange(len(dates)), index=pd.DatetimeIndex(dates))
        mkt_arr = d.groupby("date")["ret"].mean().reindex(
            pd.DatetimeIndex(dates)).to_numpy(dtype="float64")
        pn = d["permno"].to_numpy()
        starts = np.flatnonzero(np.r_[True, pn[1:] != pn[:-1]])
        ends = np.r_[starts[1:], len(pn)]
        blocks = {int(pn[s]): (int(s), int(e)) for s, e in zip(starts, ends)}
        ret_all = d["ret"].to_numpy(dtype="float64")
        di_all = d_idx.reindex(pd.DatetimeIndex(d["date"])).to_numpy()
        sub = ek[(ek["year"] >= lo) & (ek["year"] <= hi)]
        for permno, g in sub.groupby("permno", sort=False):
            blk = blocks.get(int(permno))
            if blk is None:
                continue
            s, e = blk
            di, r = di_all[s:e], ret_all[s:e]
            for rec in g.itertuples(index=False):
                pos = int(np.searchsorted(dates, np.datetime64(rec.observed_at.normalize()),
                                          side="left"))
                if pos >= len(dates):
                    continue
                j = int(np.searchsorted(di, pos, side="left"))
                if j >= len(di):
                    continue
                out = {"permno": int(permno), "event_month": rec.event_month,
                       "items": rec.items_joined}
                for tag, h in (("5", 5), ("21", 21)):
                    a0, a1 = j + 2, j + 2 + h      # PIT-safe entry, as F1's e2
                    if a1 > len(r):
                        out[f"car_mkt_{tag}"] = np.nan
                        continue
                    rr, mm = r[a0:a1], mkt_arr[di[a0:a1]]
                    ok = np.isfinite(rr) & np.isfinite(mm)
                    if ok.sum() < max(1, int(0.6 * h)):
                        out[f"car_mkt_{tag}"] = np.nan
                        continue
                    out[f"car_mkt_{tag}"] = float(
                        np.prod(1.0 + rr[ok]) - np.prod(1.0 + mm[ok]))
                rows.append(out)
        del d
        gc.collect()
        log(f"    8-K cohort {lo}-{hi}: {len(rows):,} rows so far")
    car = pd.DataFrame(rows)
    if car.empty:
        return {}, {"status": "REFUSED", "why": "no 8-K row matched a price block"}
    items = (car["items"].astype("string").str.split(",")
             .explode().str.strip().dropna())
    counts = items.value_counts()
    keep = [i for i in counts.index if counts[i] >= 2000]
    cells = {}
    for item in keep:
        has = car["items"].astype("string").str.contains(
            rf"(?:^|,)\s*{item.replace('.', chr(92) + '.')}\s*(?:,|$)", regex=True,
            na=False)
        for tag in ("5", "21"):
            col = f"car_mkt_{tag}"
            d2 = car.loc[car[col].notna(), ["event_month", col]].assign(has=has[car[col].notna()])
            blocks_ = {}
            for m, g in d2.groupby("event_month", sort=True):
                a = g.loc[g["has"], col]
                b = g.loc[~g["has"], col]
                if len(a) < 5 or len(b) < 20:
                    continue
                blocks_[m] = float(a.mean() - b.mean())
            s = pd.Series(blocks_, dtype="float64").sort_index()
            if len(s) < 8:
                cells[f"item_{item}|{tag}d"] = {
                    "verdict": "CANNOT DETERMINE", "date_blocks": int(len(s))}
                continue
            t = _t(s)
            cells[f"item_{item}|{tag}d"] = {
                "n_filings_with_item": int(counts[item]),
                "date_blocks_n_effective": int(len(s)),
                "mean_vs_other_8K_same_month_pct": _r(float(s.mean()) * 100, 4),
                "t_on_date_blocks": _r(t, 3),
                "p_two_sided": _p_two_sided(t),
                "mde_and_power": mde_block(s),
                "eras": era_table(s),
            }
    note = {
        "rows_with_a_car": int(len(car)),
        "date_blocks": int(car["event_month"].nunique()),
        "items_graded": keep,
        "items_dropped_under_2000_filings": [str(i) for i in counts.index if i not in keep],
        "control": ("every OTHER 8-K filing in the same event month -- NOT the "
                    "market. The sample is survivor-conditioned, and only a "
                    "within-sample contrast differences that out."),
        "entry": "close of session +1 after EDGAR acceptance (the e2 convention)",
        "window_start_year": 2017,
        "why_2017": ("the collector's median coverage_start is 2016-02-09; before "
                     "it, an absent filing is TRUNCATION and a family count would "
                     "be a statement about the collector"),
    }
    return cells, note


# ------------------- stage 6: the families as BOOKS, through N1's constructions

def attach_to_panel(df: pd.DataFrame, tape: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Carry each event feature onto the monthly panel, PIT.

    THE PIT RULE, AND THE TWO DAYS.
    A panel row for month m is decided at its `entry_date`. The announcement it
    may use is the LATEST one with `anndats <= entry_date - 2 calendar days`.
    Two days, not zero, for the same reason the e2 clock exists: IBES carries no
    time of day, so an announcement dated `entry_date` may have landed after the
    close of the session the book enters on. One day would still be a lookahead
    across a weekend; two is the cheapest bound that is right under both timings.
    """
    d = df[["permno", "month", "entry_date"]].copy()
    d["permno"] = d["permno"].astype("int64")
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    d["_cut"] = d["entry_date"] - pd.Timedelta(days=2)
    feats = ["sue_pct", "gap", "reac_pct", "sue_abs_pct", "reac_abs_pct",
             "cell_big_surprise_small_reaction", "hist_accel", "hist_mean_8",
             "hist_sd_8", "hist_mag_8", "hist_reversals_8", "hist_persistence",
             "hist_trend_8"]
    t = tape[["permno", "anndats"] + feats].dropna(subset=["anndats"]).copy()
    t["permno"] = t["permno"].astype("int64")
    d = d.sort_values("_cut", kind="mergesort")
    t = t.sort_values("anndats", kind="mergesort")
    merged = pd.merge_asof(d, t, left_on="_cut", right_on="anndats", by="permno",
                           direction="backward", allow_exact_matches=True)
    merged["days_since_announcement"] = (
        merged["_cut"] - merged["anndats"]).dt.days
    merged = merged.set_index(d.index)
    out = df.copy()
    for c in feats + ["days_since_announcement"]:
        out[c] = merged[c].reindex(out.index)
    fresh = out["days_since_announcement"] <= 90
    note = {
        "panel_rows": int(len(out)),
        "rows_with_an_announcement": int(out["sue_pct"].notna().sum()),
        "rows_with_one_in_the_last_90_days": int((out["sue_pct"].notna() & fresh).sum()),
        "share_fresh": _r(float((out["sue_pct"].notna() & fresh).mean()), 4),
        "median_days_since_announcement": _r(
            float(out["days_since_announcement"].median()), 1),
        "pit": ("merge_asof BACKWARD on entry_date - 2 days, by permno. A row whose "
                "only announcement is later than its cut carries NaN, never the "
                "next quarter's number."),
    }
    return out, note


def build_signals(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Turn the event features into the monthly selector columns a book ranks on.

    Every column is a within-month cross-sectional rank, so a book built on it
    is comparable with the incumbents in `N1_construction_books.json`, which are
    also `__xs` columns.
    """
    fresh = (df["days_since_announcement"] <= 90)
    very_fresh = (df["days_since_announcement"] <= 35)
    # F1 PEAD -- the standing surprise, only while the quarter is live
    df["_pead"] = df["sue_pct"].where(fresh)
    # F3 the expectation-reaction GAP
    df["_gap"] = df["gap"].where(fresh)
    # F1b THE ANNOUNCEMENT REACTION ITSELF. Added AFTER the event study showed
    # it is the only era-stable cell in the document (§9), which makes it
    # post-hoc: allowed under EXPLORE DIRTY for a PRODUCT_EXPERIMENT, and
    # charged to the book family, which grows 72 -> 78 cells because of it.
    df["_reac"] = df["reac_pct"].where(fresh)
    # F3b the named cell, signed: big surprise, small reaction, traded in the
    #     surprise's own direction; everything else is flat
    df["_gapcell"] = (np.sign(df["sue_pct"]).where(
        (df["cell_big_surprise_small_reaction"] == 1) & fresh))
    # F5 history
    df["_accel"] = df["hist_accel"].where(fresh)
    df["_persist"] = df["hist_persistence"].where(fresh)
    df["_mag"] = df["hist_mag_8"].where(fresh)
    df["_disp"] = (-df["hist_sd_8"]).where(fresh)          # LOW dispersion = high score
    df["_trend"] = df["hist_trend_8"].where(fresh)
    df["_revers"] = (-df["hist_reversals_8"]).where(fresh)
    df["_hmean"] = df["hist_mean_8"].where(fresh)
    # F2 revision-on-event vs revision-off-event
    rev = df["net_rev_4w__xs"] if "net_rev_4w__xs" in df.columns else None
    if rev is not None:
        df["_rev_on"] = rev.where(very_fresh)
        df["_rev_off"] = rev.where(~very_fresh)
        df["_rev_all"] = rev

    names = {
        "pead_sue": "_pead", "reaction": "_reac", "gap": "_gap", "gap_cell": "_gapcell",
        "hist_accel": "_accel", "hist_persistence": "_persist",
        "hist_magnitude": "_mag", "hist_low_dispersion": "_disp",
        "hist_trend": "_trend", "hist_few_reversals": "_revers",
        "hist_mean": "_hmean",
    }
    if rev is not None:
        names |= {"rev_on_event": "_rev_on", "rev_off_event_CONTROL": "_rev_off",
                  "rev_all_CONTROL": "_rev_all"}
    built = {}
    for out_name, raw in names.items():
        s = df[raw]
        n = int(s.notna().sum())
        if n < 20_000:
            built[out_name] = {"status": "SKIPPED", "non_null_rows": n}
            continue
        df[out_name] = df.groupby("month")[raw].rank(pct=True).astype("float32")
        built[out_name] = {"status": "ok", "non_null_rows": n,
                           "coverage_share": _r(n / len(df), 4)}
    df.drop(columns=[c for c in names.values() if c in df.columns], inplace=True)
    return df, {
        "selectors_built": built,
        "freshness_gates": {"fresh": "announcement within 90 days of the cut",
                            "very_fresh": "within 35 days -- the revision-ON-event gate"},
        "note": ("`rev_off_event_CONTROL` and `rev_all_CONTROL` are the matched "
                 "controls for `rev_on_event`: if the on-event book is no better "
                 "than the same revision column everywhere, 'on event' bought "
                 "nothing and the family closes."),
    }


def exit_attribution(weights: dict, admissible: dict) -> dict:
    """Typed exits (invariant 17), derived from the book's own weight path.

    A name that leaves the book either fell out of the hold band while still
    admissible (RANK_DECAY) or left the admissible cross-section entirely
    (UNIVERSE_EXIT -- delisted, dropped below the dollar-volume floor, or lost
    its score). Nothing here is a stop or a target: a monthly rank book has no
    stop, and pretending it does would be a typed exit that never fires.
    """
    months = sorted(weights)
    if len(months) < 2:
        return {"verdict": "CANNOT DETERMINE", "why": "fewer than two months"}
    counts = {"RANK_DECAY": 0, "UNIVERSE_EXIT": 0}
    held, spans = 0, []
    entered: dict[int, int] = {}
    for i in range(1, len(months)):
        prev, cur = weights[months[i - 1]], weights[months[i]]
        pset = {int(k) for k in prev}
        cset = {int(k) for k in cur}
        adm = admissible.get(months[i], set())
        for name in pset - cset:
            counts["RANK_DECAY" if name in adm else "UNIVERSE_EXIT"] += 1
            if name in entered:
                spans.append(i - entered.pop(name))
        for name in cset - pset:
            entered[name] = i
        held += len(cset)
    tot = sum(counts.values()) or 1
    return {
        "exits_typed": counts,
        "share": {k: _r(v / tot, 4) for k, v in counts.items()},
        "mean_realised_hold_months": _r(float(np.mean(spans)), 2) if spans else None,
        "median_realised_hold_months": _r(float(np.median(spans)), 2) if spans else None,
        "positions_still_open_at_end": len(entered),
        "note": ("a monthly rank book has exactly two ways to lose a name. No "
                 "stop, no target and no deadline is reported, because none is "
                 "armed -- a typed exit that cannot fire is a broken gate."),
    }


def grade_book(bk: dict, rf: pd.Series, *, label: str, construction: str,
               df: pd.DataFrame, pred_col: str, admissible: dict) -> tuple[dict, pd.Series]:
    """One book -> BETA FIRST, then the two rulers, the four stages, the eras."""
    from learner import fundamental_law as FL
    ser = bk.get("_series")
    if ser is None or not len(ser.get("net", [])):
        return ({"label": label, "verdict": "CANNOT DETERMINE",
                 "why": "the book produced no month"}, pd.Series(dtype=float))
    net = ser["net"].astype("float64")
    mkt = ser["market"].reindex(net.index).astype("float64")
    turn = ser["turnover"].reindex(net.index).astype("float64")
    rfs = rf.reindex(net.index).fillna(0.0)
    reg = ols_market_model(net - rfs, mkt - rfs, lag=NW_LAG)
    beta = reg.get("beta")
    if beta is None:
        return ({"label": label, "verdict": "CANNOT DETERMINE", "regression": reg},
                pd.Series(dtype=float))
    bm = float(beta) * mkt + (1.0 - float(beta)) * rfs
    ex_bm = (net - bm).dropna()
    ex_raw = (net - mkt).dropna()
    mean_turn = float(turn.mean())
    t_bm = _t(ex_bm)
    blk = {
        "label": label,
        "beta": _r(beta, 4),
        "t_beta_minus_1_hac": reg.get("t_beta_minus_1_hac"),
        "construction": construction,
        "months": int(len(net)),
        "first_month": str(net.index[0]), "last_month": str(net.index[-1]),
        "cost_bps_per_side": bk.get("cost_bps_per_side"),
        "mean_names_per_month": bk.get("mean_names_per_month"),
        "mean_turnover": _r(mean_turn, 4),
        "implied_mean_holding_months": _r(1.0 / mean_turn, 2) if mean_turn > 0 else None,
        "annual_cost_line_pct": _r(mean_turn * 2 * (bk.get("cost_bps_per_side") or 0)
                                   / 10_000.0 * 12 * 100, 3),
        "terminal_wealth_net": bk.get("terminal_wealth_net"),
        "terminal_wealth_market_same_months": bk.get("terminal_wealth_market_same_months"),
        "PRIMARY_beta_matched": {
            "annualised_pct": _r(float(ex_bm.mean()) * 12 * 100, 3),
            "t_paired": _r(t_bm, 3),
            "p_two_sided": _p_two_sided(t_bm),
        },
        "SECONDARY_raw_market": {
            "annualised_pct": _r(float(ex_raw.mean()) * 12 * 100, 3),
            "t_paired": _r(_t(ex_raw), 3),
        },
        "mde_and_power_on_the_beta_matched_excess": mde_block(ex_bm),
        "eras": era_table(ex_bm),
    }
    w = bk.get("_weights")
    if w:
        blk["fundamental_law"] = FL.receipt(
            df[["month", "permno", pred_col, "fwd_1m"]].dropna(subset=[pred_col]),
            pred_col, w, net=net, benchmark=bm, beta=float(beta))
        blk["typed_exit_attribution"] = exit_attribution(w, admissible)
    return blk, ex_bm


# ------------------------------------------------------------------- the run

def run(*, do_coverage: bool = True, do_events: bool = True, do_books: bool = True,
        rebuild_tape: bool = False, verbose: bool = True,
        receipt_path: Path | None = None) -> dict:
    from scripts import w3_neural_floored as W3B

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    # WRITE AFTER EVERY STAGE, not only at the end. The first version of this
    # function lost twenty minutes of finished stages to an AttributeError on
    # its LAST line -- the same shape as the news pull that died at 83.6% with
    # nothing on disk (BUILD_2026-09-07b_E1_NEWS_PULLER.md).
    rpath = receipt_path or (OUT_DIR / "R4_event_families.json")

    def _save(o: dict) -> None:
        tmp = rpath.with_suffix(".tmp")
        tmp.write_text(json.dumps(o, indent=1, default=str), encoding="utf-8")
        tmp.replace(rpath)
    t0 = time.perf_counter()
    tracker = RP.InputTracker()
    out: dict = {
        "job": "R4_event_families",
        "lane": "E3 (roadmap ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md block E)",
        "licence": "PRODUCT_EXPERIMENT -- a screen. It licenses BUILDING a book; it is not a claim.",
        "question": ("do the event families -- PEAD on several clocks, "
                     "revision-on-event, the surprise-reaction gap, 8-K item "
                     "families and earnings-surprise HISTORY -- carry anything "
                     "once beta, costs, expected return and multiplicity are "
                     "taken off them?"),
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": W3B.free_gb(),
        "eras": "1999-2007 / 2008-2015 / 2016-2024 (learner.long_panel.ERAS), NEVER pooled",
    }

    ib, ibnote = load_ibes(tracker)
    ek, eknote = load_eightk(tracker)
    out["sources"] = {"ibes": ibnote, "eightk": eknote}
    _save(out)

    if do_coverage:
        log("  stage 1: coverage ...")
        out["STAGE_1_COVERAGE"] = stage1_coverage(ib, ek, tracker)
        _save(out)

    tape = pd.DataFrame()
    if do_events:
        if rebuild_tape or not EVENTS_PARQUET.exists():
            log("  stage 2: building the event tape ...")
            tape, roll = build_event_tape_all(ib, tracker, log=log)
            tape, fnote = attach_surprise_features(tape)
            tape.to_parquet(EVENTS_PARQUET, index=False)
            out["STAGE_2_TAPE"] = roll | {"features": fnote}
        else:
            tape = pd.read_parquet(EVENTS_PARQUET)
            tracker.opened(EVENTS_PARQUET)
            out["STAGE_2_TAPE"] = {"status": "read from disk",
                                   "path": str(EVENTS_PARQUET),
                                   "events": int(len(tape)),
                                   "date_blocks": int(tape["event_month"].nunique())}
            if "sue_pct" not in tape.columns:
                # A tape written by the raw builder carries the CARs but not the
                # derived features. DERIVE them rather than fail on a missing
                # column three stages later.
                tape, fnote = attach_surprise_features(tape)
                tape.to_parquet(EVENTS_PARQUET, index=False)
                out["STAGE_2_TAPE"]["features"] = fnote
                out["STAGE_2_TAPE"]["features_note"] = (
                    "derived on read -- the tape on disk carried CARs only")

        log("  stage 3: PEAD on several clocks ...")
        pead: dict = {}
        for basis in ("raw", "mkt", "bo", "ab"):
            for tag in [str(c) for c in CLOCKS] + ["next_ann"]:
                for entry in (2, 1):
                    col = f"car_{basis}_{tag}_e{entry}"
                    if col not in tape.columns:
                        continue
                    key = f"{basis}|{tag}|e{entry}"
                    c = cell(tape, "sue_pct", col, label=f"PEAD|sue_decile_spread|{key}")
                    c.pop("_series", None)
                    pead[key] = c
        out["STAGE_3_PEAD_MULTICLOCK"] = pead
        _save(out)

        log("  stage 4: the surprise x reaction gap ...")
        gap: dict = {}
        for tag in ("5", "21", "60", "next_ann"):
            for basis in ("mkt", "bo"):
                col = f"car_{basis}_{tag}_e2"
                if col not in tape.columns:
                    continue
                c = cell(tape, "gap", col, label=f"GAP|decile_spread|{basis}|{tag}")
                c.pop("_series", None)
                gap[f"gap|{basis}|{tag}"] = c
        # the NAMED cell: large |surprise|, small |reaction|, traded in the
        # surprise's own direction, against everything else
        named: dict = {}
        for tag in ("5", "21", "60"):
            for basis in ("mkt", "bo"):
                col = f"car_{basis}_{tag}_e2"
                if col not in tape.columns:
                    continue
                d = tape[["event_month", col, "cell_big_surprise_small_reaction",
                          "sue_pct"]].dropna()
                d = d.assign(signed=np.sign(d["sue_pct"]) * d[col])
                blocks = {}
                for m, g in d.groupby("event_month", sort=True):
                    a = g.loc[g["cell_big_surprise_small_reaction"] == 1, "signed"]
                    b = g.loc[g["cell_big_surprise_small_reaction"] == 0, "signed"]
                    if len(a) < 5 or len(b) < 40:
                        continue
                    blocks[m] = float(a.mean() - b.mean())
                s = pd.Series(blocks, dtype="float64").sort_index()
                t = _t(s)
                named[f"big_surprise_small_reaction|{basis}|{tag}"] = {
                    "date_blocks_n_effective": int(len(s)),
                    "mean_pct_vs_every_other_event_same_month": _r(float(s.mean()) * 100, 4)
                    if len(s) else None,
                    "t_on_date_blocks": _r(t, 3), "p_two_sided": _p_two_sided(t),
                    "mde_and_power": mde_block(s), "eras": era_table(s),
                    "cell_share_of_events": _r(
                        float(tape["cell_big_surprise_small_reaction"].mean()), 4),
                    "what_it_is": ("|SUE| in the top quintile of its month AND "
                                   "|reaction| in the bottom quintile, traded in "
                                   "the surprise's direction, minus the same "
                                   "signed trade on every other event that month"),
                }
        out["STAGE_4_SURPRISE_x_REACTION"] = {"gap_decile_spread": gap,
                                              "the_named_cell": named}
        _save(out)

        log("  stage 5: earnings-surprise history ...")
        hist: dict = {}
        for sig in ("hist_accel", "hist_persistence", "hist_mag_8", "hist_sd_8",
                    "hist_trend_8", "hist_reversals_8", "hist_mean_8"):
            for tag in ("21", "next_ann"):
                for basis in ("mkt", "bo"):
                    col = f"car_{basis}_{tag}_e2"
                    if col not in tape.columns or sig not in tape.columns:
                        continue
                    c = cell(tape, sig, col, label=f"HIST|{sig}|{basis}|{tag}")
                    c.pop("_series", None)
                    hist[f"{sig}|{basis}|{tag}"] = c
        out["STAGE_5_EARNINGS_HISTORY"] = hist
        _save(out)

        log("  stage 6: 8-K item families (the declared slice) ...")
        cells8, note8 = eightk_families(ek, tracker, log=log)
        out["STAGE_6_EIGHTK_ITEM_FAMILIES"] = {"note": note8, "cells": cells8}
        _save(out)

    if do_books:
        log("  stage 7: the families as BOOKS, through N1's constructions ...")
        out["STAGE_7_BOOKS"] = books_stage(tape, tracker, log=log)
        _save(out)

    # ------------------------------------------------- family-wide correction
    log("  stage 8: family size, family-max p, BH-FDR, Holm ...")
    out["STAGE_8_MULTIPLICITY"] = multiplicity(out)
    out["memory_free_gb_after"] = W3B.free_gb()
    out["elapsed_s"] = _r(time.perf_counter() - t0, 1)
    RP.attach(out, sys.argv, {
        "first_year": FIRST_YEAR, "last_year": LAST_YEAR,
        "clocks": list(CLOCKS), "next_ann_cap": NEXT_ANN_CAP,
        "market_model_window": [MM_START, MM_END, MM_MIN],
        "constructions": [f"k={k}|{w}|hold={h or 'none'}" for k, w, h in CONSTRUCTIONS],
        "costs_bps_per_side": list(COSTS), "deciles": DECILES, "nw_lag": NW_LAG,
    }, tracker)
    return out


#: A p rounded to 8 dp can print as exactly 0.0 for a t of 40. Zero is FALSY in
#: Python, and the first version of `survives` here read `(p or 1.0) <= 0.05`,
#: which turned the strongest cell in the document into "does not survive". The
#: floor makes the number honest AND keeps it truthy.
P_FLOOR = 1e-12


def _walk_cells(node, prefix=""):
    """Every graded cell in the receipt, with its p and the SIGN of its t.

    The family is ENUMERATED, per invariant 16 -- a new name cannot mint fresh
    budget. The sign travels with the p because "the smallest p in the family"
    is not "the best cell": a book that loses 4.9%/yr at t -3.18 has a small p.
    """
    if isinstance(node, dict):
        if node.get("p_two_sided") is not None:
            p = max(float(node["p_two_sided"]), P_FLOOR)
            t = node.get("t_on_date_blocks", node.get("t_paired"))
            yield prefix.strip("."), p, (float(t) if t is not None else None)
        for k, v in node.items():
            if k.startswith("_") or k in ("mde_and_power", "eras", "BETA_FIRST",
                                          "mde_and_power_on_the_beta_matched_excess"):
                continue
            yield from _walk_cells(v, f"{prefix}.{k}")


def multiplicity(out: dict) -> dict:
    """FAMILY SIZE, FAMILY-MAX p, BH-FDR for screening, Holm for export."""
    fams = {
        "F1_PEAD_multiclock": out.get("STAGE_3_PEAD_MULTICLOCK", {}),
        "F3_surprise_x_reaction": out.get("STAGE_4_SURPRISE_x_REACTION", {}),
        "F5_earnings_history": out.get("STAGE_5_EARNINGS_HISTORY", {}),
        "F4_eightk_items": out.get("STAGE_6_EIGHTK_ITEM_FAMILIES", {}).get("cells", {}),
        "F2_and_books": out.get("STAGE_7_BOOKS", {}).get("cells", {}),
    }
    res: dict = {}
    all_p: dict[str, float] = {}
    all_t: dict[str, float | None] = {}

    def _block(p: dict[str, float], sgn: dict[str, float | None]) -> dict:
        h, b = holm(p), bh_fdr(p)
        best = min(p, key=p.get)
        pos = {k: v for k, v in p.items() if (sgn.get(k) or 0.0) > 0}
        best_pos = min(pos, key=pos.get) if pos else None
        surv = sorted(k for k in p
                      if h.get(k) is not None and h[k] <= 0.05 and (sgn.get(k) or 0) > 0)
        return {
            "family_size_cells_looked_at": len(p),
            "FAMILY_MAX_p": _r(max(p.values()), 8),
            "smallest_raw_p_ANY_SIGN": {"cell": best, "p": _r(p[best], 13),
                                        "t": _r(sgn.get(best), 3)},
            "smallest_raw_p_POSITIVE_t": (
                {"cell": best_pos, "p": _r(pos[best_pos], 13),
                 "t": _r(sgn.get(best_pos), 3), "holm_p": h.get(best_pos),
                 "survives_holm_0.05": bool(h.get(best_pos) is not None
                                            and h[best_pos] <= 0.05)}
                if best_pos else {"note": "no cell in this family has a positive t"}),
            "holm_EXPORT_survivors_positive_t": surv[:25],
            "n_holm_survivors_positive_t": len(surv),
            "bh_fdr_SCREEN_q0.05_rejected": b["rejected"][:25],
            "n_rejected_bh": len(b["rejected"]),
        }

    for fam, node in fams.items():
        cells = list(_walk_cells(node))
        if not cells:
            res[fam] = {"family_size_cells_looked_at": 0, "note": "no graded cell"}
            continue
        p = {k: v for k, v, _ in cells}
        sgn = {k: t for k, _, t in cells}
        res[fam] = _block(p, sgn)
        for k in p:
            all_p[f"{fam}.{k}"] = p[k]
            all_t[f"{fam}.{k}"] = sgn[k]
    res["ACROSS_EVERY_FAMILY"] = (_block(all_p, all_t) if all_p else
                                  {"family_size_cells_looked_at": 0})
    res["ACROSS_EVERY_FAMILY"]["note"] = (
        "every cell LOOKED AT is counted -- including the ones that read as "
        "nothing and the ones on a return basis that was only ever a control. "
        "That is invariant 16. A small p with a NEGATIVE t is a book that lost "
        "money reliably, which is why the two are reported separately.")
    return res


def books_stage(tape: pd.DataFrame, tracker: RP.InputTracker, log=print) -> dict:
    """The families expressed as BOOKS on the graded panel, N1's constructions.

    NOTHING IS FOLDED INTO `arena_composite`. A family that survives here becomes
    its OWN `PRODUCT_EXPERIMENT` book (CLAUDE.md, THE BOTTLENECK): a weight in a
    composite hides the only question worth asking, which is whether its errors
    are DIFFERENT errors.
    """
    from learner import benchmark as BM
    from learner import evaluate as E
    from learner import neural_long as N
    from scripts import w3_neural_floored as W3B
    from scripts.labor_a1_shadow_grader import _month_windows, _window_leg

    if tape.empty:
        if not EVENTS_PARQUET.exists():
            return {"status": "REFUSED", "why": "no event tape on disk"}
        tape = pd.read_parquet(EVENTS_PARQUET)
        tracker.opened(EVENTS_PARQUET)

    df, uni, fp = W3B.load_universe(verbose=False)
    tracker.opened(LONG_PANEL)
    df, anote = attach_to_panel(df, tape)
    df, snote = build_signals(df)

    months_all = pd.Index(sorted(df["month"].dropna().unique()))
    win = _month_windows(df)
    try:
        rf, rf_note = _window_leg(BM.cash().returns.dropna().astype("float64"),
                                  win, months_all)
        rf_note["source"] = "learner.benchmark.cash() -- pinned FF daily RF, OFFLINE"
    except Exception as exc:                                        # noqa: BLE001
        rf = pd.Series(0.0, index=months_all)
        rf_note = {"available": False, "why": f"{type(exc).__name__}: {exc}",
                   "declared": "rf = 0; only the intercept's level moves"}

    # the admissible cross-section per month, under the SAME floor the book uses
    floor = N.TRADABLE_FLOOR_USD
    dv = np.expm1(df["log_dollar_vol_20d"].to_numpy(dtype="float64"))
    adm_df = df.loc[dv >= floor, ["month", "permno"]]
    admissible = {m: set(g["permno"].astype("int64"))
                  for m, g in adm_df.groupby("month", sort=True)}

    selectors = [k for k, v in snote["selectors_built"].items()
                 if isinstance(v, dict) and v.get("status") == "ok"]
    cells: dict = {}
    for name in selectors:
        for (k, wgt, hk) in CONSTRUCTIONS:
            for bps in COSTS:
                key = f"{name}|k={k}|{wgt}|hold={hk or 'none'}|{int(bps)}bps"
                try:
                    bk = E.book(df, name, k=k, weight=wgt, cost_bps=bps,
                                ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                tradable_floor=floor, hold_k=hk,
                                return_series=True, return_weights=True)
                except SystemExit as exc:
                    cells[key] = {"label": key, "verdict": "REFUSED", "why": str(exc)}
                    continue
                blk, _ = grade_book(
                    bk, rf, label=key, df=df, pred_col=name, admissible=admissible,
                    construction=(f"top-{k} {wgt}"
                                  + (f", hold until rank > {hk}" if hk
                                     else ", rebuilt every month (the incumbent control)")))
                cells[key] = blk
        log(f"    {name}: {len([c for c in cells if c.startswith(name + '|')])} cells")

    # DSR on the best beta-matched cell, deflated by the WHOLE family
    ranked = [(k, v) for k, v in cells.items()
              if isinstance(v.get("PRIMARY_beta_matched"), dict)
              and v["PRIMARY_beta_matched"].get("t_paired") is not None]
    dsr = {"verdict": "CANNOT DETERMINE", "why": "no gradeable cell"}
    best = None
    if ranked:
        # the annualised Sharpe of a cell's BETA-MATCHED excess, from its own
        # paired t and month count: t = mean/(sd/sqrt(n)) => SR_ann = t/sqrt(n)*sqrt(12)
        def _sr(v):
            n_m = v.get("months") or 0
            t = v["PRIMARY_beta_matched"]["t_paired"]
            return (t / math.sqrt(n_m) * math.sqrt(12)) if n_m else None
        best = max(ranked, key=lambda kv: kv[1]["PRIMARY_beta_matched"]["t_paired"])
        dsr = deflated_sharpe(_sr(best[1]), [_sr(v) for _, v in ranked],
                              best[1]["months"]) | {"cell": best[0]}

    del df
    gc.collect()
    return {
        "universe": {k: uni[k] for k in
                     ("dollar_volume_floor_usd_per_day", "rows_after", "months_after",
                      "median_names_per_month_after") if k in uni},
        "universe_fingerprint_sha256": fp,
        "pit_attach": anote,
        "selectors": snote,
        "risk_free_leg": rf_note,
        "constructions": [f"k={k}|{w}|hold={h or 'none'}" for k, w, h in CONSTRUCTIONS],
        "costs_bps_per_side": list(COSTS),
        "cells": cells,
        "best_cell_by_beta_matched_t": best[0] if best else None,
        "deflated_sharpe_of_the_best": dsr,
        "NOT_A_COMPOSITE": ("no column here is added to `arena_composite`. A family "
                            "that survives becomes its own PRODUCT_EXPERIMENT book."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--coverage", action="store_true", help="stage 1 only")
    ap.add_argument("--events", action="store_true", help="stages 1-6, no panel books")
    ap.add_argument("--books", action="store_true", help="stage 7 only (needs the tape)")
    ap.add_argument("--rebuild-tape", action="store_true")
    ap.add_argument("--redo-multiplicity", action="store_true",
                    help="recompute stage 8 from the receipt on disk; no data is re-read")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    path = Path(a.out) if a.out else (OUT_DIR / "R4_event_families.json")
    if a.redo_multiplicity:
        if not path.exists():
            print(f"REFUSED: {path} does not exist", flush=True)
            return 1
        res = json.loads(path.read_text(encoding="utf-8"))
        res["STAGE_8_MULTIPLICITY"] = multiplicity(res)
        res["stage_8_recomputed_utc"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print(f"stage 8 recomputed in {path}", flush=True)
        return 0
    only = a.coverage or a.events or a.books
    try:
        res = run(do_coverage=(not only) or a.coverage or a.events,
                  do_events=(not only) or a.events or a.books,
                  do_books=(not only) or a.books,
                  rebuild_tape=a.rebuild_tape, receipt_path=path)
    except Exception as exc:                                        # noqa: BLE001
        # A failure APPENDS to whatever the stages already wrote; it never
        # replaces it. Losing finished stages to a crash in a later one is how
        # the first run of this job threw away twenty minutes.
        res = {}
        if path.exists():
            try:
                res = json.loads(path.read_text(encoding="utf-8"))
            except Exception:                                       # noqa: BLE001
                res = {}
        res |= {"job": "R4_event_families", "status": "FAILED",
                "why": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}
    path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}", flush=True)
    return 0 if res.get("status") != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

