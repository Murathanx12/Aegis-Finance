"""Three theory cells at $0 (CHUNK C12, 2026-10-06), each a DECLARED hyp_lab cell.

    python -m scripts.hyp_theory_cells --cell hi52         --part declare [--run <R>]
    python -m scripts.hyp_theory_cells --cell hi52         --part run     --run <R>
    python -m scripts.hyp_theory_cells --cell insider_hold --part declare|run [--run <R>]
    python -m scripts.hyp_theory_cells --cell beat_streak  --part declare|run [--run <R>]

The three READY_TO_CELL rows of `docs/research_notes/2026-10-06/snowball_and_theory_objects_2026-10-06.md`
§3 (rows 12, 3, 13):

* ``hi52``          standalone price location (price / 52-week high, `strategy_library` rule `hi52`
                    and its two library siblings) on CRSP, read on the FAIR-TWIN board's four
                    columns (`scripts.hyp_twin_board`, run FT_2026-10-06_1): pure selection, fair
                    twin net, net minus market. A RE-READ of an already-run rule, no new search.
* ``insider_hold``  an officer/director open-market buy whose buyers file NO sale of the same
                    stock within 90 calendar days. "No sale yet" is only knowable on day 90, so
                    the entry is the OPEN of the first CRSP session after buy + 90 days; the
                    control is the buy-then-sold cohort entered the same way, and the size-band
                    equal-weight return (matched non-event names) is the benchmark. Spread cost
                    beside the gross on every cell.
* ``beat_streak``   consecutive IBES EPS beats (actual > consensus mean, quarterly): does the
                    post-announcement drift SHRINK as the streak grows (the bar rises)? Drift
                    by streak length, entered at the open two business days after the
                    announcement, with the [e-1, e+1] reaction printed beside it.

Every cell: the declaration (cells, inputs, splits, decision rule) is written and sha256-hashed
BEFORE the run; the run REFUSES on a hash mismatch or an input-file change; the receipt carries the
run id in its name and is never overwritten; by hold year and leave-one-year-out are printed on
every primary. Verdict vocabulary: CANDIDATE / FAILED_VARIANT / CANNOT_DISTINGUISH (and REFUSED
for a run that could not happen). Never STOP. The verdict and receipt are written back into the
hyp_lab ledger, so the families' posteriors (D6) learn from them.

Licence PRODUCT_EXPERIMENT. $0: no LLM, no network. Reuses `crsp_event_bridge.link_permno`,
`hyp_investable.spread_stats / survives`, the fair-twin series and the insider-events engine shape.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
CR_OUT = OPT / "crsp_rebuild"
OUT = OPT / "hyp_lab"
INS = OPT / "sec_insider" / "insider_events_v1.parquet"
SURP = WRDS / "bulk" / "tr_ibes__surpsumu.parquet"
IBLINK = WRDS / "bulk" / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet"
PANEL_RUN = "2026-09-29T075640Z"
CS_RUN = "FU_2026-09-29T0855Z"
FAIR_RUN = "FT_2026-10-06_1"
FAIR_DIR = OUT / f"fair_twin_series_{FAIR_RUN}"

MIN_FREE_GB = 4.0            # the brief: run only with >= 4 GB free
POLL_S, MAX_WAIT_S = 120, 2400   # poll every 2 minutes, up to 40 minutes, then REFUSE

VOCAB = ("CANDIDATE", "FAILED_VARIANT", "CANNOT_DISTINGUISH", "REFUSED")
DECISION = (
    "Primary series = monthly mean of the declared quantity, indexed by the month the position is "
    "held (hyp_investable.spread_stats: t on non-overlapping 3-month blocks, MDE = 2.8 SE). "
    "CANDIDATE iff design mean > 0 AND validate mean > 0 with t >= 2 AND a strict majority of "
    "validate years > 0 AND the leave-one-year-out worst validate mean > 0. FAILED_VARIANT iff "
    "validate mean <= 0, or validate t < 2 with validate MDE <= the effect worth having "
    "(max(design mean, min_effect)). Otherwise CANNOT_DISTINGUISH. Late (2017-2024) is read last "
    "and never decides. A cell whose sign is 'design' multiplies the series by the sign of its "
    "design mean first (the design fold fixes the direction; validate decides).")

CELLS = {
    "hi52": {
        "family": "price_location", "target": "return",
        "title": "Standalone 52-week-high nearness on CRSP, fair twin",
        "mechanism": "Anchoring on the 52-week high makes investors under-react to good news near the high "
                     "(George-Hwang); names nearest their high keep drifting up.",
        "precursor": "price / 52-week high at the month-end decision date (CRSP, strategy_library rule hi52, k=20)",
        "separation_from_beta": "fair matched twin (size x vol x 12-1 momentum cell mix, same cost convention): "
                                "the momentum beta the high carries is in the twin",
        "refutation": "validate (2009-2016) fair-twin-net mean <= 0, or t < 2 with MDE below the effect worth having",
        "inputs": {r: f"backend/data/optimus/hyp_lab/fair_twin_series_{FAIR_RUN}/{r}.parquet"
                   for r in ("hi52", "hi52_large", "hi52_q")},
        "primary": "hi52: fair_twin_net (monthly, net of own-turnover costs, vs the fair twin)",
        "reported": ["pure_selection", "fair_twin_net", "net_minus_market"] ,
        "splits": {"design": ("1991-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
                   "late": ("2017-01-01", "2024-12-31")},
        "sign": "+1", "min_effect": 0.002,
        "honesty": ("Declared AFTER the 2026-09-29 library board printed hi52 FAILED_VARIANT (rule - twin21 "
                    "-0.33%/mo, t -2.44, LIB_2026-09-29T0802Z) and after a partial view of the FT_2026-10-06_1 "
                    "board row. This is a re-read of an already-run rule under the hyp_lab decision rule on the "
                    "fair twin, not a fresh test: search count +0, and a CANDIDATE here would be a finding to "
                    "test forward, never a prior. The snowball note's 'standalone hi52 never run on CRSP' was "
                    "wrong: it was run, by name, in LIB_2026-09-29T0802Z."),
    },
    "insider_hold": {
        "family": "insider_hold", "target": "return",
        "title": "Insider buy with no sale by the buyers within 90 days",
        "mechanism": "An insider who buys and then does not sell is signalling conviction rather than "
                     "liquidity or diversification timing; the conviction cohort should drift more than "
                     "insiders who buy and quickly sell.",
        "precursor": "officer/director open-market buy (Form 4, not 10b5-1) on day t, and NO open-market sale "
                     "of the same stock filed by any of those buyers in (t, t+90 days]; knowable at t+90",
        "separation_from_beta": "benchmark = equal-weight CRSP common stocks of the same size band (matched "
                                "non-event names) over the same sessions; control cohort = buy-then-sold events "
                                "entered the same way",
        "refutation": "validate (2009-2016) HOLD-cohort net abnormal 63-session return vs the size band <= 0, "
                      "or t < 2 with MDE below the effect worth having",
        "inputs": {"insider": "backend/data/optimus/sec_insider/insider_events_v1.parquet",
                   "crsp_daily": "backend/data/optimus/wrds/crsp_dsf_<year>.parquet (2006-2024)",
                   "bands": f"backend/data/optimus/crsp_rebuild/library_panel_{PANEL_RUN}.parquet",
                   "spreads": f"backend/data/optimus/crsp_rebuild/followups_daily_{CS_RUN}.parquet"},
        "event": "firm-level: the first officer/director open-market buy on a permno after >= 90 days with none; "
                 "buyers = the CIKs buying that permno on that public day; HOLD iff none of them files an "
                 "open-market sale of that permno with public date in (t, t+90]; SOLD otherwise",
        "entry": "OPEN of the first CRSP session strictly after t + 90 calendar days (when 'no sale' is knowable)",
        "horizons": [21, 63],
        "primary": "HOLD cohort, H=63, net (minus a round trip of max(Corwin-Schultz, flat band)) abnormal vs size band",
        "reported": ["HOLD/SOLD x H21/H63 x market/band, gross and net, mean round trip", "HOLD - SOLD gross"],
        "splits": {"design": ("2006-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
                   "late": ("2017-01-01", "2024-12-31")},
        "sign": "+1", "min_effect": 0.005,
        "honesty": ("Prior from memory: insider CLUSTER drift is real gross (t ~6) and EQUALS the spread "
                    "(insider_events_RESULTS_IE_2026-09-30T0135Z: gross +1.1-1.5%/5 sessions, round trip 136 bps). "
                    "The no-subsequent-sale cut was not in any of the 15 library insider rules nor the IE cells."),
    },
    "beat_streak": {
        "family": "earnings_streak", "target": "return",
        "title": "Consecutive EPS beats: does post-announcement drift shrink as the streak grows",
        "mechanism": "Expectations ratchet: after several beats the market prices the next beat in, so the "
                     "post-announcement drift of a streak beat is smaller than that of a first beat (or, the "
                     "rival: streaks signal persistent under-reaction and drift is larger).",
        "precursor": "number of consecutive quarters with IBES actual EPS > consensus mean, ending at this "
                     "announcement (knowable at the announcement)",
        "separation_from_beta": "drift is abnormal vs the size band; the primary is a within-month DIFFERENCE "
                                "(streak >= 3 beats minus first beats), so market and band beta cancel",
        "refutation": "validate (2009-2016) signed (streak>=3 - streak 1) 63-session drift difference <= 0, "
                      "or t < 2 with MDE below the effect worth having",
        "inputs": {"surprise": "backend/data/optimus/wrds/bulk/tr_ibes__surpsumu.parquet (EPS, QTR, usfirm=1)",
                   "link": "backend/data/optimus/wrds/bulk/wrdsapps_link_crsp_ibes__ibcrsphist.parquet",
                   "crsp_daily": "backend/data/optimus/wrds/crsp_dsf_<year>.parquet (1993-2024)",
                   "bands": f"backend/data/optimus/crsp_rebuild/library_panel_{PANEL_RUN}.parquet",
                   "spreads": f"backend/data/optimus/crsp_rebuild/followups_daily_{CS_RUN}.parquet"},
        "event": "one per (IBES ticker, fiscal quarter) announcement; beat = actual > surpmean; streak = "
                 "consecutive beats ending here, reset by a miss/meet or a quarter gap > 4 months; permno via "
                 "the ibcrsphist row active on anndats",
        "entry": "OPEN of the first CRSP session strictly after anndats + 1 business day",
        "horizons": [21, 63],
        "primary": "monthly mean of (H=63 gross abnormal drift vs size band | streak >= 3) minus (same | streak == 1), "
                   "sign fixed by the design fold",
        "reported": ["drift by streak bucket miss/1/2/3/4/5+ per split, H21 and H63", "[e-1,e+1] reaction by bucket",
                     "streak >= 3 net vs band and market (the tradeable leg)"],
        "splits": {"design": ("1994-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
                   "late": ("2017-01-01", "2024-12-31")},
        "sign": "design", "min_effect": 0.003,
        "honesty": ("ear_drift / ear_mom (PEAD continuation) decay post-2009 and are DEPRIORITIZED on CRSP; "
                    "none of the 12 earnings_event library rules conditioned on a streak count."),
    },
    # C16 (2026-10-07): DECLARED ONLY -- no runner exists yet; `--part run` refuses by name.
    "fiscal_year_end_spending": {
        "family": "fiscal_calendar", "target": "return", "declared_only": True, "fy_gate": "basket_stat",
        "source": "public_flow_sensors_2026-10-07",
        "source_ref": "docs/research_notes/2026-10-07/public_flow_sensors_2026-10-07.md",
        "title": "Federal fiscal-year-end spending: federal contractors in August-September",
        "mechanism": "Agencies obligate unspent fiscal-year funds before Sept 30 (use it or lose it; fiscal Q4 "
                     "carries a disproportionate share of contract obligations), producing an order/revenue "
                     "uptick for federal-exposed contractors that the market may under-anticipate.",
        "precursor": "(review F8, 2026-10-07) this is a CALENDAR effect conditional on federal exposure: the "
                     "only inputs knowable before Aug 1 are the calendar and the name's federal revenue share "
                     "from its last 10-K customer segment ending before Aug 1 (Compustat seg_customer GOVDOM / "
                     "business-segment sales). Fiscal-Q4 agency obligations are NOT knowable on Aug 1 (only "
                     "July has happened and DoD's July publishes ~October); the agency-month snapshots are a "
                     "forward diagnostic of the mechanism, never a precursor",
        "separation_from_beta": "within-name: the same names' own Oct-Jul monthly excess return is the baseline, "
                                "so name beta and sector beta cancel; benchmark = CRSP value-weighted market; "
                                "control cohort = matched non-federal names of the same size band and SIC2 over "
                                "the same Aug-Sep months (a calendar effect common to all stocks is not this one)",
        "refutation": "validate (FY2017-FY2024) Aug-Sep minus own-baseline excess return <= 0, or t < 2 with MDE "
                      "below the effect worth having; AND (dose) the high-federal-share tercile must not be "
                      "below the low tercile -- an effect that does not scale with federal exposure is not "
                      "this mechanism",
        "universe": "crosswalk tickers (backend/data/crosswalks/usaspending_recipient_ticker.yaml) linked to CRSP "
                    "common stock (shrcd 10/11) by ticker over the name's date range, restricted to names with "
                    "Compustat GOVDOM customer-segment rows; federal share = GOVDOM sales / total segment sales "
                    "in the last fiscal year ending before the decision date",
        "inputs": {"crosswalk": "backend/data/crosswalks/usaspending_recipient_ticker.yaml",
                   "crsp_names": "backend/data/optimus/wrds/bulk/crsp__stocknames.parquet",
                   "comp_names": "backend/data/optimus/wrds/bulk/comp__names.parquet",
                   "seg_customer": "backend/data/optimus/wrds/bulk/compseg__seg_customer.parquet",
                   "crsp_daily": "backend/data/optimus/wrds/crsp_dsf_<year>.parquet (2008-2024)",
                   "agency_months": "backend/data/optimus/public_flow/tables/gov_agency_month_obligations.jsonl "
                                    "(forward snapshots only; history needs the bulk archive -- named, not assumed)"},
        "event": "one per (permno, fiscal year): the Aug 1 - Sep 30 window; statistical unit for the primary = "
                 "the FISCAL YEAR (one equal-weight basket per FY), because every name's window is the same "
                 "calendar months and name-months are cross-sectionally correlated",
        "entry": "OPEN of the first CRSP session on or after Aug 1; exit CLOSE of the last session on or before Sep 30",
        "horizons": ["Aug1-Sep30 (~42 sessions)"],
        "primary": "per FY: equal-weight basket (Aug-Sep compounded excess vs VW market) minus the same basket's "
                   "mean monthly excess over the prior Oct-Jul x 2 months; net of one round trip "
                   "(max(Corwin-Schultz, flat band))",
        "reported": ["by FY and leave-one-FY-out", "federal-share terciles (dose)",
                     "matched non-federal control over the same months", "gross and net"],
        "splits": {"design": ("2008-10-01", "2016-09-30"), "validate": ("2016-10-01", "2024-09-30")},
        "sign": "+1", "min_effect": 0.005,
        "honesty": ("No corpse found for fiscal-year-end spend in hyp_lab or the strategy library; the nearest "
                    "siblings (macro_lead_lag oil/yield cells) ended CANNOT_DISTINGUISH, so the prior is modest. "
                    "Only 8 fiscal years per split: the gate's name-month MDE is an i.i.d. LOWER bound and the "
                    "honest unit is the fiscal year -- with 8 validate FYs the comparison is likely unpowered; "
                    "that is printed, not hidden. The agency-month precursor has NO point-in-time history "
                    "before the first snapshot (2026-10-07): any backtest that uses today's revised monthly "
                    "totals as if known in August is look-ahead and is barred. The gate links by TICKER over each "
                    "CRSP name range, so a ticker reused by an unrelated firm inside 2008-2024 is counted (the "
                    "gate's n is an upper bound); the runner must link by the crosswalk company's gvkey/permco. "
                    "REVIEW F7/F8 (2026-10-07): the universe is now linked by permco with crosswalk dates, and "
                    "the gate is computed at the FISCAL-YEAR unit from the DESIGN fold. DISCLOSURE: while "
                    "building that gate the builder printed the per-FY statistic for ALL FYs 2009-2024, "
                    "validate included; the history validate fold is therefore SEEN and can no longer confirm "
                    "anything -- a positive would need forward fiscal years (FY2027+)."),
    },
    # Review F8 (2026-10-07): the within-year DOSE version -- same months, high minus low tercile of
    # federal revenue share -- has more independent variation than the calendar. DECLARED ONLY.
    "fiscal_year_end_dose": {
        "family": "fiscal_calendar", "target": "return", "declared_only": True, "fy_gate": "dose_stat",
        "source": "public_flow_sensors_2026-10-07",
        "source_ref": "docs/reviews/REVIEW_2026-10-07_C16_PUBLIC_FLOW_SENSORS.md",
        "title": "Fiscal-year-end spending, within-year dose: high vs low federal revenue share in Aug-Sep",
        "mechanism": "If use-it-or-lose-it obligations lift federal contractors in Aug-Sep, the lift should scale "
                     "with the share of revenue that is federal; a common calendar effect does not.",
        "precursor": "federal revenue share (GOVDOM customer sales / business-segment sales) from the last 10-K "
                     "segment year ending before Aug 1 of the FY -- knowable before the window opens",
        "separation_from_beta": "a within-FY difference of two baskets over the SAME months: market, calendar and "
                                "the contractor sector's common move cancel; each leg is also net of its own "
                                "Oct-Jul baseline",
        "refutation": "validate (FY2017-FY2024) top-minus-bottom tercile Aug-Sep statistic <= 0, or t < 2 with MDE "
                      "below the effect worth having",
        "universe": "as fiscal_year_end_spending (permco-linked, crosswalk-dated, GOVDOM names), names with a "
                    "federal share in that FY; terciles within each FY",
        "inputs": {"crosswalk": "backend/data/crosswalks/usaspending_recipient_ticker.yaml",
                   "crsp_names": "backend/data/optimus/wrds/bulk/crsp__stocknames.parquet",
                   "comp_names": "backend/data/optimus/wrds/bulk/comp__names.parquet",
                   "seg_customer": "backend/data/optimus/wrds/bulk/compseg__seg_customer.parquet",
                   "crsp_monthly": "backend/data/optimus/wrds/bulk/crsp__msf.parquet",
                   "market": "backend/data/optimus/wrds/ff_factors_monthly.parquet"},
        "event": "one per fiscal year: the top-minus-bottom tercile spread of the per-FY statistic",
        "entry": "Aug 1 - Sep 30, monthly CRSP returns",
        "horizons": ["Aug1-Sep30"],
        "primary": "per FY: [top tercile basket stat] minus [bottom tercile basket stat], stat = Aug-Sep "
                   "compounded excess vs FF market minus 2 x mean monthly excess over the preceding Oct-Jul",
        "reported": ["by FY", "leave-one-FY-out", "tercile counts"],
        "splits": {"design": ("2008-10-01", "2016-09-30"), "validate": ("2016-10-01", "2024-09-30")},
        "sign": "+1", "min_effect": 0.005,
        "honesty": ("Declared after review F8 asked for it. DISCLOSURE: the builder printed this per-FY spread "
                    "for ALL FYs 2009-2024 (validate included) while building the FY-unit gate; the history "
                    "validate fold is SEEN, so a history read cannot confirm -- forward FYs only."),
    },
}


# ── small helpers ─────────────────────────────────────────────────────────────

def say(*a) -> None:
    print(*a, flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha_of(body: dict) -> str:
    """sha256 of the declaration body (everything but the hash and the write time)."""
    core = {k: v for k, v in body.items() if k not in ("sha256", "written_utc")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def file_sha(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_declaration(doc: dict) -> tuple[bool, str]:
    """A declared cell runs only on the declaration it was hashed with."""
    if not doc.get("sha256"):
        return False, "declaration carries no sha256"
    got = sha_of(doc)
    if got != doc["sha256"]:
        return False, f"declaration hash mismatch: stored {doc['sha256'][:16]}, recomputed {got[:16]}"
    return True, "ok"


def decl_path(cell: str, run: str) -> Path:
    return OUT / f"theory_{cell}_DECLARATION_{run}.json"


def result_path(cell: str, run: str) -> Path:
    return OUT / f"theory_{cell}_RESULTS_{run}.json"


def _write_new(p: Path, doc: dict) -> None:
    """Receipts are never overwritten: temp -> verify -> replace, refusing an existing name."""
    if p.exists():
        raise FileExistsError(f"REFUSED: {p.name} exists (receipts are never overwritten)")
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(p)


def free_gb() -> float:
    try:
        from scripts.hyp_lab import _free_ram_gb  # noqa: PLC0415
        return float(_free_ram_gb())
    except Exception:  # noqa: BLE001
        return float("nan")


def wait_for_ram(floor: float = MIN_FREE_GB, poll_s: int = POLL_S, max_wait_s: int = MAX_WAIT_S,
                 probe=free_gb, sleep=time.sleep) -> tuple[bool, float]:
    """Poll (do not compete): True once free RAM >= floor; False after max_wait_s."""
    t0 = time.monotonic()
    while True:
        r = probe()
        if r == r and r >= floor:
            return True, r
        if time.monotonic() - t0 >= max_wait_s:
            return False, r
        say(f"  free RAM {r:.2f} GB < {floor} GB; polling again in {poll_s}s")
        sleep(poll_s)


# ── the verdict (one rule for the three cells) ───────────────────────────────

def loo_worst_window(s: pd.Series, lo: str, hi: str) -> Optional[float]:
    from backend.services import hyp_investable as HI  # noqa: PLC0415
    w = HI.window(s, lo, hi)
    if w.empty:
        return None
    yrs = HI.hold_index(w.index).year
    uk = sorted(set(yrs))
    if len(uk) < 2:
        return None
    return float(min(w[yrs != y].mean() for y in uk))


def theory_verdict(design: dict, validate: dict, loo_validate: Optional[float], min_effect: float) -> dict:
    from backend.services import hyp_investable as HI  # noqa: PLC0415
    dm, vm, vt, vmde = (design.get("mean_monthly"), validate.get("mean_monthly"),
                        validate.get("t_blocks"), validate.get("mde_monthly"))
    if vm is None or vt is None or vmde is None:
        return {"verdict": "REFUSED", "reason": "validate window has no usable estimate"}
    ok, fails = HI.survives(design, validate)
    if ok and loo_validate is not None and loo_validate > 0:
        return {"verdict": "CANDIDATE", "powered": True, "reason": f"design {dm:+.5f}, validate {vm:+.5f} t {vt:.2f}, "
                                                  f"years {validate.get('years_positive')}, LOO worst {loo_validate:+.5f}"}
    if ok:
        fails = fails + [f"leave-one-year-out worst validate mean {loo_validate} <= 0"]
    worth = max(float(dm) if dm is not None else 0.0, float(min_effect))
    powered = bool(vmde <= worth)       # review 2026-10-06 F6: only a powered negative is evidence
    if vm <= 0:
        return {"verdict": "FAILED_VARIANT", "reason": f"validate mean {vm:+.5f} <= 0", "fails": fails,
                "powered": powered}
    if vt < 2 and vmde <= worth:
        return {"verdict": "FAILED_VARIANT", "fails": fails, "powered": powered,
                "reason": f"validate t {vt:.2f} < 2 and MDE {vmde:.5f} <= effect worth having {worth:.5f}"}
    return {"verdict": "CANNOT_DISTINGUISH", "fails": fails, "powered": powered,
            "reason": f"validate {vm:+.5f} t {vt:.2f}; MDE {vmde:.5f} vs effect worth having {worth:.5f}"}


def read_series(s: pd.Series, splits: dict, sign: str, min_effect: float) -> dict:
    """Stats on every split + full, by hold year + LOO, and the verdict on the signed series."""
    from backend.services import hyp_investable as HI  # noqa: PLC0415
    s = pd.Series(s, dtype=float).dropna().sort_index()
    raw_design = HI.spread_stats(s, *splits["design"])
    sg = 1.0
    if sign == "design":
        sg = 1.0 if (raw_design.get("mean_monthly") or 0.0) >= 0 else -1.0
    x = s * sg
    st = {k: HI.spread_stats(x, lo, hi) for k, (lo, hi) in splits.items()}
    st["full"] = HI.spread_stats(x)
    loo = {k: loo_worst_window(x, lo, hi) for k, (lo, hi) in splits.items()}
    v = theory_verdict(st["design"], st["validate"], loo["validate"], min_effect)
    return {"sign_applied": sg, "stats": st, "loo_worst": loo, **v}


# ── the hyp_lab ledger link ─────────────────────────────────────────────────

def ledger_row(cell: str, run: str) -> dict:
    from backend.services import hyp_lab as L  # noqa: PLC0415
    c = CELLS[cell]
    return L.make_hypothesis(title=c["title"], mechanism=c["mechanism"], precursor=c["precursor"],
                             separation_from_beta=c["separation_from_beta"], refutation=c["refutation"],
                             target=c["target"], family=c["family"],
                             source=c.get("source", "theory_objects_2026-10-06"),
                             source_ref=c.get("source_ref", "docs/research_notes/2026-10-06/"
                                                            "snowball_and_theory_objects_2026-10-06.md"),
                             cell_type=f"theory_{cell}", params={"run": run}, split=c["splits"],
                             negative_informative=True, expected_power=0.6, cpu_min=20.0,
                             notes="declared cell (scripts.hyp_theory_cells); $0")


# ── declare ───────────────────────────────────────────────────────────────────

def declaration(cell: str, run: str) -> dict:
    c = CELLS[cell]
    body = {"schema": "hyp_lab/theory_cell_declaration/1", "cell": cell, "run": run,
            "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decision": DECISION,
            "verdict_vocabulary": list(VOCAB), **{k: v for k, v in c.items()}}
    if cell == "hi52":
        body["input_sha256"] = {r: file_sha(REPO / p) for r, p in c["inputs"].items()}
    if cell in ("fiscal_year_end_spending", "fiscal_year_end_dose"):
        body["input_sha256"] = {r: file_sha(REPO / p) for r, p in c["inputs"].items()
                                if r in ("crosswalk", "crsp_names", "comp_names", "seg_customer")}
    return body


# ── the declaration gate (review 2026-10-06 F2: a base-rate and power check BEFORE hashing) ──

def declaration_gate(treated: pd.Series, min_effect: float, *, event_sd: float | None = None,
                     max_share: float | None = None, max_mde_mult: float | None = None,
                     labels: tuple[str, str] = ("treated", "control")) -> dict:
    """`treated`: one bool per event (the separating variable, built from LABELS only, no outcome).
    Prints the class split and the control's labels-only MDE (2.8 x event_sd / sqrt(n_control):
    i.i.d., unblocked, so a LOWER bound on the real MDE). Refuses when one class holds more than
    `max_share` of events (the variable does not separate) or the control MDE exceeds
    `max_mde_mult` x the effect worth having (the comparison can never be read)."""
    from backend import config as C  # noqa: PLC0415
    event_sd = C.THEORY_GATE_EVENT_SD if event_sd is None else event_sd
    max_share = C.THEORY_GATE_MAX_CLASS_SHARE if max_share is None else max_share
    max_mde_mult = C.THEORY_GATE_MAX_MDE_MULT if max_mde_mult is None else max_mde_mult
    s = pd.Series(treated).dropna().astype(bool)
    n, n_t = int(len(s)), int(s.sum())
    n_c = n - n_t
    share = (max(n_t, n_c) / n) if n else 1.0
    mde_c = (2.8 * event_sd / math.sqrt(n_c)) if n_c > 0 else float("inf")
    reasons = []
    if share > max_share:
        reasons.append(f"one class holds {share:.1%} of {n:,} events (> {max_share:.0%}): the separating "
                       f"variable does not separate")
    if mde_c > max_mde_mult * min_effect:
        reasons.append(f"control ({labels[1]}, n={n_c:,}) labels-only MDE {mde_c:.4f} > {max_mde_mult:g} x "
                       f"effect worth having {min_effect:.4f}: the comparison can never be read")
    return {"n_events": n, f"n_{labels[0]}": n_t, f"n_{labels[1]}": n_c,
            "class_split": {labels[0]: round(n_t / n, 4) if n else None, labels[1]: round(n_c / n, 4) if n else None},
            "control_mde_lower_bound": round(mde_c, 5), "event_sd_preset": event_sd,
            "max_class_share": max_share, "max_mde_mult": max_mde_mult,
            "refused": bool(reasons), "reasons": reasons}


def gate_labels(cell: str) -> Optional[tuple[pd.Series, tuple[str, str]]]:
    """The separating variable per cell, from labels only (no returns are read). None = no class
    split (hi52 is a rule read against its matched twin)."""
    if cell == "insider_hold":
        B, S = _insider_frames()
        E = insider_hold_events(B, S)
        E = E[(E["gate"] >= "2006-01-01") & (E["gate"] <= "2024-09-30")]
        return E["hold"], ("HOLD", "SOLD")
    if cell == "beat_streak":
        Q = pd.read_parquet(SURP, columns=["ticker", "measure", "fiscalp", "pyear", "pmon", "usfirm", "anndats",
                                           "actual", "surpmean"],
                            filters=[("measure", "=", "EPS"), ("fiscalp", "=", "QTR")])
        Q = Q[Q["usfirm"].astype(float) == 1]
        Q["anndats"] = pd.to_datetime(Q["anndats"], errors="coerce")
        Q = beat_streaks(Q)
        Q = Q[(Q["anndats"] >= "1993-06-01") & (Q["anndats"] <= "2024-09-30")]
        Q = Q[(Q["streak"] >= 3) | (Q["streak"] == 1)]
        return Q["streak"] >= 3, ("STREAK3P", "STREAK1")
    if cell in ("fiscal_year_end_spending", "fiscal_year_end_dose"):
        return fiscal_ye_labels()
    return None


def _crosswalk_ticker_windows() -> dict[str, Optional[str]]:
    """ticker -> earliest valid_from over its crosswalk entries (None = open)."""
    import yaml  # noqa: PLC0415
    inp = CELLS["fiscal_year_end_spending"]["inputs"]
    cw = yaml.safe_load((REPO / inp["crosswalk"]).read_text(encoding="utf-8"))["entries"]
    out: dict[str, Optional[str]] = {}
    for e in cw:
        t, vf = str(e["ticker"]).upper(), (str(e["valid_from"])[:10] if e.get("valid_from") else None)
        if t not in out:
            out[t] = vf
        elif out[t] is not None and (vf is None or vf < out[t]):
            out[t] = vf
    return out


def fiscal_ye_universe() -> pd.DataFrame:
    """Labels only (no returns). Review F7 (2026-10-07): link by COMPANY, not by
    ticker string. For each crosswalk ticker the company is the CRSP permco that
    holds the ticker most recently; every name row of that permco is kept (so
    Harris/HRS, AmerisourceBergen/ABC, UTX, old SAIC count as their company) and
    any OTHER permco that once used the ticker (Cortex as COR, MDRNA as MRNA,
    Protective Life as PL) is dropped. One permno per permco (HEI's two share
    classes counted once). Months before the ticker's earliest crosswalk
    `valid_from` are dropped. `govdom` = Compustat carries GOVDOM customer rows."""
    inp = CELLS["fiscal_year_end_spending"]["inputs"]
    win = _crosswalk_ticker_windows()
    N = pd.read_parquet(REPO / inp["crsp_names"], columns=["permno", "permco", "ticker", "namedt",
                                                           "nameenddt", "shrcd"])
    N = N[N["shrcd"].isin([10, 11])].copy()
    N["namedt"], N["nameenddt"] = pd.to_datetime(N["namedt"]), pd.to_datetime(N["nameenddt"])
    hold = N[N["ticker"].isin(list(win))].sort_values("nameenddt")
    cur = hold.groupby("ticker").tail(1)[["ticker", "permco", "permno"]]
    rows = []
    for _, c in cur.iterrows():
        comp = N[N["permco"] == c["permco"]]
        # one permno per company: the one that carries the ticker most recently
        comp = comp[comp["permno"] == c["permno"]].copy()
        comp["xw_ticker"] = c["ticker"]
        comp["valid_from"] = win.get(c["ticker"])
        rows.append(comp)
    U = pd.concat(rows, ignore_index=True) if rows else N.iloc[0:0]
    cn = pd.read_parquet(REPO / inp["comp_names"], columns=["gvkey", "tic"])
    sc = pd.read_parquet(REPO / inp["seg_customer"], columns=["gvkey", "ctype"])
    gov = set(sc.loc[sc["ctype"] == "GOVDOM", "gvkey"].astype(str))
    gtic = set(cn.loc[cn["gvkey"].astype(str).isin(gov), "tic"].astype(str).str.upper())
    U["govdom"] = U["xw_ticker"].isin(gtic)
    return U


def fiscal_ye_name_months() -> pd.DataFrame:
    """(permno, month) listed in FY2009-FY2024 inside the crosswalk window, GOVDOM names only."""
    U = fiscal_ye_universe()
    U = U[U["govdom"]]
    months = pd.period_range("2008-10", "2024-09", freq="M")
    out = []
    for _, r in U.iterrows():
        lo, hi = r["namedt"].to_period("M"), r["nameenddt"].to_period("M")
        vf = pd.Timestamp(r["valid_from"]).to_period("M") if r["valid_from"] else None
        for m in months:
            if lo <= m <= hi and (vf is None or m >= vf):
                out.append((int(r["permno"]), r["xw_ticker"], m))
    return pd.DataFrame(out, columns=["permno", "ticker", "month"]).drop_duplicates(["permno", "month"])


def fiscal_ye_labels() -> tuple[pd.Series, tuple[str, str]]:
    """One bool per (permno, month): True = August or September."""
    M = fiscal_ye_name_months()
    return M["month"].dt.month.isin([8, 9]).reset_index(drop=True), ("AUG_SEP", "OTHER_MONTHS")


def _fed_share_by_ticker_fy() -> pd.DataFrame:
    """GOVDOM sales / business-segment sales from the last fiscal year ending
    before Aug 1 of each FY's calendar year (knowable before the window opens)."""
    inp = CELLS["fiscal_year_end_spending"]["inputs"]
    sc = pd.read_parquet(REPO / inp["seg_customer"], columns=["gvkey", "ctype", "salecs", "datadate"])
    sa = pd.read_parquet(REPO / "backend/data/optimus/wrds/bulk/compseg__seg_annfund.parquet",
                         columns=["gvkey", "stype", "sales", "datadate", "srcdate"])
    cn = pd.read_parquet(REPO / inp["comp_names"], columns=["gvkey", "tic"])
    g = sc[sc["ctype"] == "GOVDOM"].groupby(["gvkey", "datadate"], as_index=False)["salecs"].sum()
    sa = sa[sa["stype"] == "BUSSEG"].sort_values("srcdate").drop_duplicates(
        ["gvkey", "datadate", "stype"], keep="last")
    t = sa.groupby(["gvkey", "datadate"], as_index=False)["sales"].sum()
    m = g.merge(t, on=["gvkey", "datadate"])
    m = m[m["sales"] > 0]
    m["share"] = (m["salecs"] / m["sales"]).clip(0, 1)
    m = m.merge(cn.assign(tic=cn["tic"].astype(str).str.upper()), on="gvkey")
    rows = []
    for fy in range(2009, 2025):
        cut = pd.Timestamp(f"{fy}-08-01")
        x = m[pd.to_datetime(m["datadate"]) < cut].sort_values("datadate").groupby("tic").tail(1)
        rows += [(r["tic"], fy, float(r["share"])) for _, r in x.iterrows()]
    return pd.DataFrame(rows, columns=["ticker", "fy", "fed_share"])


def fiscal_ye_fy_series() -> pd.DataFrame:
    """Per FY: the declared primary statistic for (a) the equal-weight GOVDOM
    basket and (b) the within-year DOSE spread (top minus bottom tercile of
    federal share). stat = Aug-Sep compounded excess (vs FF market) minus 2 x the
    mean monthly excess over the preceding Oct-Jul. DESIGN FOLD ONLY is used by
    the gate (power), never validate."""
    M = fiscal_ye_name_months()
    perm = sorted(M["permno"].unique().tolist())
    R = pd.read_parquet(REPO / "backend/data/optimus/wrds/bulk/crsp__msf.parquet",
                        columns=["permno", "date", "ret"], filters=[("permno", "in", perm)])
    R["month"] = pd.to_datetime(R["date"]).dt.to_period("M")
    F = pd.read_parquet(REPO / "backend/data/optimus/wrds/ff_factors_monthly.parquet",
                        columns=["date", "mktrf", "rf"])
    F["month"] = pd.to_datetime(F["date"]).dt.to_period("M")
    F["mkt"] = F["mktrf"] + F["rf"]
    X = M.merge(R[["permno", "month", "ret"]], on=["permno", "month"]).merge(F[["month", "mkt"]], on="month")
    X["ex"] = X["ret"] - X["mkt"]
    X["fy"] = X["month"].dt.year + (X["month"].dt.month >= 10).astype(int)
    S = _fed_share_by_ticker_fy()
    X = X.merge(S, on=["ticker", "fy"], how="left")
    out = []
    for fy, g in X.groupby("fy"):
        def stat(sub: pd.DataFrame) -> Optional[float]:
            w = sub[sub["month"].dt.month.isin([8, 9])].groupby("month")["ex"].mean()
            b = sub[~sub["month"].dt.month.isin([8, 9])].groupby("month")["ex"].mean()
            if len(w) < 2 or len(b) < 6:
                return None
            return float((1 + w).prod() - 1 - 2 * b.mean())
        base = stat(g)
        sh = g.dropna(subset=["fed_share"]).drop_duplicates("permno")[["permno", "fed_share"]]
        dose = None
        if len(sh) >= 9:
            lo, hi = sh["fed_share"].quantile([1 / 3, 2 / 3])
            top = set(sh.loc[sh["fed_share"] >= hi, "permno"])
            bot = set(sh.loc[sh["fed_share"] <= lo, "permno"])
            a, b = stat(g[g["permno"].isin(top)]), stat(g[g["permno"].isin(bot)])
            dose = (a - b) if a is not None and b is not None else None
        out.append({"fy": int(fy), "basket_stat": base, "dose_stat": dose,
                    "n_names": int(g["permno"].nunique()), "n_with_share": int(len(sh))})
    return pd.DataFrame(out)


def fy_unit_gate(design: pd.Series, n_validate: int, min_effect: float, *,
                 max_mde_mult: Optional[float] = None) -> dict:
    """Review F8: the gate at the cell's OWN unit, the fiscal year. sd of the
    per-FY statistic over the DESIGN fold; MDE = 2.8 sd / sqrt(n_validate);
    REFUSES when MDE > max_mde_mult x the effect worth having."""
    from backend import config as C  # noqa: PLC0415
    mult = C.THEORY_GATE_MAX_MDE_MULT if max_mde_mult is None else max_mde_mult
    x = pd.Series(design, dtype=float).dropna()
    sd = float(x.std(ddof=1)) if len(x) >= 3 else float("nan")
    mde = 2.8 * sd / math.sqrt(n_validate) if n_validate > 0 and sd == sd else float("inf")
    reasons = []
    if not (mde <= mult * min_effect):
        reasons.append(f"FY-unit MDE {mde:.4f} (design sd {sd:.4f} over {len(x)} FYs, {n_validate} validate "
                       f"FYs) > {mult:g} x effect worth having {min_effect:.4f}: the comparison can never be read")
    return {"unit": "fiscal year", "n_design_fy": int(len(x)), "n_validate_fy": int(n_validate),
            "design_sd": round(sd, 5) if sd == sd else None, "mde": round(mde, 5) if mde != float("inf") else None,
            "max_mde_mult": mult, "min_effect": min_effect, "refused": bool(reasons), "reasons": reasons,
            "note": "sd from the DESIGN fold only (power, not a result); validate untouched"}


def part_declare(cell: str, run: str, *, ledger: bool = True, labels=None) -> int:
    """Declare (hash) a cell. Before hashing: the row goes through hyp_lab.dedupe() (a rule
    already run on CRSP is recorded as `reread_of` and counts +0 in the posterior; a duplicate
    of a ledger row refuses), and the declaration gate prints the class split and the
    control's MDE and REFUSES a cell whose separating comparison cannot be read."""
    from backend.services import hyp_lab as L  # noqa: PLC0415
    p = decl_path(cell, run)
    body = declaration(cell, run)
    if cell == "hi52" and any(v is None for v in body["input_sha256"].values()):
        say(f"REFUSED: a fair-twin input is missing: {body['input_sha256']}")
        return 2
    fyg = CELLS[cell].get("fy_gate")
    if fyg and labels is None:
        S = fiscal_ye_fy_series()
        lo, hi = CELLS[cell]["splits"]["design"]
        dfy = S[(S["fy"] >= int(lo[:4]) + 1) & (S["fy"] <= int(hi[:4]))][fyg]
        vlo, vhi = CELLS[cell]["splits"]["validate"]
        n_val = int(((S["fy"] >= int(vlo[:4]) + 1) & (S["fy"] <= int(vhi[:4]))).sum())
        g = fy_unit_gate(dfy, n_val, CELLS[cell]["min_effect"])
        say(f"  FY gate ({fyg}): design sd {g['design_sd']}  MDE {g['mde']}  vs {g['max_mde_mult']}x"
            f"{g['min_effect']}  {'REFUSED' if g['refused'] else 'ok'}")
        body["fy_gate"] = g
        if g["refused"]:
            gp = OUT / f"theory_{cell}_GATE_REFUSED_{run}.json"
            if not gp.exists():
                _write_new(gp, {"schema": "hyp_lab/theory_cell_gate/1", "cell": cell, "run": run,
                                "written_utc": _now(), "verdict": "UNPOWERED_AT_DECLARATION", "fy_gate": g})
            say("REFUSED (UNPOWERED_AT_DECLARATION): " + "; ".join(g["reasons"]))
            return 2
    lab = labels if labels is not None else gate_labels(cell)
    if lab is not None:
        g = declaration_gate(lab[0], CELLS[cell]["min_effect"], labels=lab[1])
        say(f"  gate: split {g['class_split']}  control MDE >= {g['control_mde_lower_bound']:.4f}  "
            f"{'REFUSED' if g['refused'] else 'ok'}")
        if g["refused"]:
            gp = OUT / f"theory_{cell}_GATE_REFUSED_{run}.json"
            if not gp.exists():
                _write_new(gp, {"schema": "hyp_lab/theory_cell_gate/1", "cell": cell, "run": run,
                                "written_utc": _now(), "gate": g})
            say("REFUSED: " + "; ".join(g["reasons"]))
            return 2
        body["gate"] = g
    else:
        body["gate"] = {"not_applicable": "no class split: the rule is read against its matched twin"}
    row = ledger_row(cell, run)
    row["declared_reread"] = True
    row = L.dedupe([row], L.load_state() if ledger else {})[0]
    if row.get("status") == "DUPLICATE_IN_LEDGER":
        say(f"REFUSED: duplicate of ledger row {row.get('dedup', {}).get('nearest_ledger')}")
        return 2
    if row.get("reread_of"):
        body["reread_of"] = row["reread_of"]
        say(f"  RE-READ of {row['reread_of']}: counts +0 in the family posterior")
    body["dedup"] = row.get("dedup")
    body["hyp_id"] = row["hyp_id"]
    body["sha256"] = sha_of(body)
    body["written_utc"] = _now()
    try:
        _write_new(p, body)
    except FileExistsError as e:
        say(str(e))
        return 2
    if ledger:
        state = L.load_state()
        if row["hyp_id"] not in state:
            L.append([row])
        L.update(row["hyp_id"], status="DECLARED", receipt=L._rel(p))
    say(f"-> {p.name} sha256 {body['sha256'][:16]} hyp {row['hyp_id']}")
    return 0


# ── the event engine (CRSP daily, the insider-events shape, vectorised) ───────

def _bands_and_spreads(start: str):
    """(K, bandmap): K = month-end panel rows (date, permno, band, rt) for the per-event round trip;
    bandmap = (permno, month) -> size band from the previous month-end, for the band EW index."""
    from backend.services import matched_twins as MT  # noqa: PLC0415
    from backend.services import xs_ranker as XR  # noqa: PLC0415
    K = pd.read_parquet(CR_OUT / f"library_panel_{PANEL_RUN}.parquet", columns=["date", "symbol", "median_dollar_vol"],
                        filters=[("date", ">=", pd.Timestamp(start))])
    K["date"] = pd.to_datetime(K["date"])
    K["permno"] = pd.to_numeric(K["symbol"], errors="coerce")
    K = K.dropna(subset=["permno"]).drop(columns=["symbol"])
    K["permno"] = K["permno"].astype("int64")
    D = pd.read_parquet(CR_OUT / f"followups_daily_{CS_RUN}.parquet", columns=["date", "permno", "cs_spread"],
                        filters=[("date", ">=", pd.Timestamp(start))])
    D["date"] = pd.to_datetime(D["date"])
    D["permno"] = pd.to_numeric(D["permno"], errors="coerce").astype("int64")
    K = K.merge(D, on=["date", "permno"], how="left")
    del D
    K["band"] = MT.size_band(K["median_dollar_vol"].to_numpy(dtype=float))
    mdv = K["median_dollar_vol"].to_numpy(dtype=float)
    flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035 for v in mdv])
    cs = np.minimum(K["cs_spread"].to_numpy(dtype=float), 0.20)
    K["rt"] = np.where(np.isfinite(cs), np.maximum(cs, flat), flat)
    bm = K[["date", "permno", "band"]].copy()
    bm["ym"] = (bm["date"] + pd.offsets.MonthBegin(1)).dt.to_period("M")
    bandmap = bm.drop_duplicates(["permno", "ym"]).set_index(["permno", "ym"])["band"]
    return K[["date", "permno", "band", "rt"]], bandmap


def _market_cum() -> tuple[pd.Series, pd.Series]:
    ff = pd.read_parquet(WRDS / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    m = (ff.set_index("date")["mktrf"] + ff.set_index("date")["rf"]).astype(float).sort_index()
    lm = np.log1p(m)
    return lm.cumsum(), lm


def _load_year(y: int, need: Optional[set]) -> Optional[pd.DataFrame]:
    f = WRDS / f"crsp_dsf_{y}.parquet"
    if not f.exists():
        return None
    X = pd.read_parquet(f, columns=["permno", "date", "ret", "prc", "openprc"])
    X["date"] = pd.to_datetime(X["date"])
    for c in ("ret", "prc", "openprc", "permno"):
        X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.dropna(subset=["permno"])
    X["permno"] = X["permno"].astype("int64")
    for c in ("ret", "prc", "openprc"):
        X[c] = X[c].astype("float32")
    return X


def event_returns(E: pd.DataFrame, horizons, years, *, reaction: bool = False) -> pd.DataFrame:
    """E: eid, permno, gate (entry = first session strictly after gate)[, rday]. Per (event, H):
    r (open of entry -> close H-1 sessions later), r_mkt, r_band (same sessions, close-to-close
    incl. the entry day), band, rt. With `reaction`, also car = [e-1, e+1] vs market around rday
    (first session >= rday)."""
    K, bandmap = _bands_and_spreads(f"{min(years) - 1}-06-01")
    E = E.sort_values("gate").reset_index(drop=True)
    E = pd.merge_asof(E, K.sort_values("date"), left_on="gate", right_on="date", by="permno",
                      direction="backward").drop(columns=["date"])
    del K
    gc.collect()
    MC, LM = _market_cum()
    need = set(E["permno"].astype("int64"))
    E["gy"] = E["gate"].dt.year
    out, band_daily = [], []
    prev = None
    for y in list(years) + [max(years) + 1]:
        te = time.time()
        X = _load_year(y, need) if y <= max(years) else None
        if X is not None:
            ym = X["date"].dt.to_period("M")
            X["band"] = bandmap.reindex(pd.MultiIndex.from_arrays([X["permno"], ym])).to_numpy()
            band_daily.append(X.dropna(subset=["ret", "band"]).groupby(["date", "band"])["ret"].mean().unstack("band"))
            cur = X[X["permno"].isin(need)][["permno", "date", "ret", "prc", "openprc"]].copy()
            del X
        else:
            cur = None
        # events gated in year y-1 are measured on rows of y-1 and y
        if prev is not None:
            ev = E[E["gy"] == y - 1]
            if len(ev):
                R = pd.concat([prev] + ([cur] if cur is not None else []), ignore_index=True)
                BD = pd.concat(band_daily).sort_index()
                BD = BD[~BD.index.duplicated()]
                out.append(_measure(ev, R, BD, MC, LM, horizons, reaction))
                del R
        prev = cur
        gc.collect()
        say(f"    {y} {time.time() - te:.0f}s ({sum(len(o) for o in out):,} rows)")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _measure(ev, R, BD, MC, LM, horizons, reaction) -> pd.DataFrame:
    R = R.sort_values(["permno", "date"]).reset_index(drop=True)
    R["pos"] = np.arange(len(R))
    lr = np.log1p(R["ret"].astype(float).fillna(0.0).to_numpy())
    cum = np.cumsum(lr)
    perm = R["permno"].to_numpy()
    dts = R["date"].to_numpy(dtype="datetime64[ns]")
    prc = np.abs(R["prc"].to_numpy(dtype=float))
    opn = np.abs(R["openprc"].to_numpy(dtype=float))
    m = pd.merge_asof(ev.sort_values("gate"), R[["date", "permno", "pos"]].sort_values("date"), left_on="gate",
                      right_on="date", by="permno", direction="forward", allow_exact_matches=False,
                      tolerance=pd.Timedelta(days=10))
    m = m.dropna(subset=["pos"]).reset_index(drop=True)
    i = m["pos"].astype(int).to_numpy()
    ok_i = np.isfinite(opn[i]) & (opn[i] > 0) & np.isfinite(prc[i])
    BC = {b: np.log1p(BD[b].fillna(0.0)).cumsum() for b in BD.columns}
    BL = {b: np.log1p(BD[b].fillna(0.0)) for b in BD.columns}
    recs = []
    for H in horizons:
        j = i + H - 1
        inb = j < len(R)
        jj = np.where(inb, j, 0)
        ok = ok_i & inb & (perm[jj] == m["permno"].to_numpy()) & \
            ((dts[jj] - dts[i]) <= np.timedelta64(int(H * 1.6) + 5, "D"))
        r = (prc[i] / np.where(opn[i] > 0, opn[i], np.nan)) * np.exp(cum[jj] - cum[i]) - 1.0
        di, dj = pd.DatetimeIndex(dts[i]), pd.DatetimeIndex(dts[jj])
        r_m = np.exp(MC.reindex(dj).to_numpy() - MC.reindex(di).to_numpy() + LM.reindex(di).fillna(0.0).to_numpy()) - 1.0
        bands = m["band"].where(m["band"].isin(list(BC)), "small").astype(str).to_numpy()
        r_b = np.full(len(m), np.nan)
        for b in set(bands):
            k = bands == b
            if b in BC:
                r_b[k] = np.exp(BC[b].reindex(dj[k]).to_numpy() - BC[b].reindex(di[k]).to_numpy()
                                + BL[b].reindex(di[k]).fillna(0.0).to_numpy()) - 1.0
        f = m.loc[ok].copy()
        f["H"] = H
        f["entry"] = di[ok]
        f["r"], f["r_mkt"], f["r_band"] = r[ok], r_m[ok], r_b[ok]
        f["rt"] = f["rt"].fillna(0.0035)
        recs.append(f)
    F = pd.concat(recs, ignore_index=True) if recs else pd.DataFrame()
    if reaction and len(F) and "rday" in F:
        e = pd.merge_asof(F[["eid", "permno", "rday"]].drop_duplicates("eid").sort_values("rday"),
                          R[["date", "permno", "pos"]].sort_values("date"), left_on="rday", right_on="date",
                          by="permno", direction="forward", tolerance=pd.Timedelta(days=5)).dropna(subset=["pos"])
        p = e["pos"].astype(int).to_numpy()
        lo, hi = p - 2, p + 1
        okr = (lo >= 0) & (hi < len(R))
        lo_, hi_ = np.where(okr, lo, 0), np.where(okr, hi, 0)
        okr &= (perm[lo_] == e["permno"].to_numpy()) & (perm[hi_] == e["permno"].to_numpy())
        stock = np.exp(cum[hi_] - cum[lo_]) - 1.0
        mk = np.exp(MC.reindex(pd.DatetimeIndex(dts[hi_])).to_numpy() - MC.reindex(pd.DatetimeIndex(dts[lo_])).to_numpy()) - 1.0
        e["car"] = np.where(okr, stock - mk, np.nan)
        F = F.merge(e[["eid", "car"]], on="eid", how="left")
    return F.drop(columns=["date", "pos"], errors="ignore")


def monthly(x: pd.DataFrame, col: str) -> pd.Series:
    """Event values -> mean by entry month, indexed at the previous month-end (hold month = entry month)."""
    s = x.groupby(x["entry"].dt.to_period("M"))[col].mean()
    s.index = s.index.to_timestamp(how="start") - pd.Timedelta(days=1)
    return s


# ── cell (b): insider buy, no sale by the buyers within 90 days ───────────────

HOLD_CHECK_DAYS = 90
REFRACTORY_DAYS = 90


def insider_hold_events(B: pd.DataFrame, S: pd.DataFrame, *, check_days: int = HOLD_CHECK_DAYS,
                        refractory_days: int = REFRACTORY_DAYS) -> pd.DataFrame:
    """B: buys (permno, pub, cik); S: sales (permno, pub, cik). Firm-level events: the first buy day
    on a permno after >= refractory_days without one; buyers = CIKs buying that permno that day.
    hold = no sale by any of those buyers with pub in (t, t + check_days]. gate = t + check_days
    (the first day 'no sale' is knowable). Uses only filings public by the gate."""
    B = B.dropna(subset=["permno", "pub", "cik"]).sort_values(["permno", "pub"])
    ev = []
    for p, g in B.groupby("permno", sort=False):
        days = np.unique(g["pub"].to_numpy(dtype="datetime64[ns]"))
        prev = None
        for d in days:
            # quiet-then-buy: the gap is measured from the previous BUY day, not the previous event
            if prev is None or d >= prev + np.timedelta64(refractory_days, "D"):
                ev.append((p, pd.Timestamp(d)))
            prev = d
    E = pd.DataFrame(ev, columns=["permno", "t"])
    if E.empty:
        return E.assign(n_buyers=[], hold=[], gate=[])
    buyers = E.merge(B.rename(columns={"pub": "t"}), on=["permno", "t"])[["permno", "t", "cik"]].drop_duplicates()
    nb = buyers.groupby(["permno", "t"])["cik"].nunique().rename("n_buyers")
    sold = buyers.merge(S.rename(columns={"pub": "spub"}), on=["permno", "cik"])
    sold = sold[(sold["spub"] > sold["t"]) & (sold["spub"] <= sold["t"] + pd.Timedelta(days=check_days))]
    sold_keys = set(zip(sold["permno"], sold["t"]))
    E = E.merge(nb.reset_index(), on=["permno", "t"], how="left")
    E["hold"] = [(p, t) not in sold_keys for p, t in zip(E["permno"], E["t"])]
    E["gate"] = E["t"] + pd.Timedelta(days=check_days)
    return E


def _insider_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["permno", "event_type", "observed_at_utc", "insider_cik", "insider_is_officer",
            "insider_is_director", "insider_plan_10b5_1"]
    A = pd.read_parquet(INS, columns=cols, filters=[("event_type", "in", ["insider_open_market_buy",
                                                                          "insider_open_market_sell"])])
    A = A.dropna(subset=["permno", "observed_at_utc", "insider_cik"])
    A["permno"] = A["permno"].astype("int64")
    A["pub"] = A["observed_at_utc"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    A = A.rename(columns={"insider_cik": "cik"})
    od = A["insider_is_officer"].fillna(False) | A["insider_is_director"].fillna(False)
    B = A[(A["event_type"] == "insider_open_market_buy") & od & (A["insider_plan_10b5_1"] != "YES")]
    S = A[A["event_type"] == "insider_open_market_sell"]
    return B[["permno", "pub", "cik"]].copy(), S[["permno", "pub", "cik"]].copy()


# ── cell (c): beat streaks ────────────────────────────────────────────────────

STREAK_GAP_MONTHS = 4


def beat_streaks(Q: pd.DataFrame) -> pd.DataFrame:
    """Q: ticker, pyear, pmon, anndats, actual, surpmean (one row per quarter). Adds `beat`
    (actual > surpmean) and `streak` (consecutive beats ending at this quarter; 0 on a miss/meet;
    a fiscal gap > STREAK_GAP_MONTHS restarts the count)."""
    q = Q.dropna(subset=["actual", "surpmean", "anndats"]).copy()
    q["pidx"] = q["pyear"].astype(int) * 12 + q["pmon"].astype(int)
    q = q.sort_values(["ticker", "pidx", "anndats"]).drop_duplicates(["ticker", "pidx"], keep="first")
    q["beat"] = q["actual"] > q["surpmean"]
    streak = np.zeros(len(q), dtype=int)
    tk, pi, bt = q["ticker"].to_numpy(), q["pidx"].to_numpy(), q["beat"].to_numpy()
    for k in range(len(q)):
        if not bt[k]:
            streak[k] = 0
        elif k > 0 and tk[k] == tk[k - 1] and 0 < pi[k] - pi[k - 1] <= STREAK_GAP_MONTHS:
            streak[k] = streak[k - 1] + 1
        else:
            streak[k] = 1
    q["streak"] = streak
    return q.drop(columns=["pidx"]).reset_index(drop=True)


def streak_bucket(s: pd.Series) -> pd.Series:
    return s.clip(upper=5).map({0: "miss", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5+"})


# ── run ───────────────────────────────────────────────────────────────────────

def _cohort_cells(x: pd.DataFrame, splits: dict, horizons, label: str) -> dict:
    """gross / net vs market and band, by split (monthly means), plus the mean round trip."""
    from backend.services import hyp_investable as HI  # noqa: PLC0415
    out = {}
    for H in horizons:
        y = x[x["H"] == H].copy()
        if y.empty:
            continue
        for bm in ("market", "band"):
            ref = y["r_mkt"] if bm == "market" else y["r_band"]
            y["g"] = y["r"] - ref
            y["n"] = y["g"] - y["rt"]
            g, n = monthly(y, "g"), monthly(y, "n")
            out[f"{label}_H{H}_{bm}"] = {
                "n_events": int(len(y)), "mean_round_trip_bps": round(float(y["rt"].mean() * 1e4), 1),
                "event_mean_gross": round(float(y["g"].mean()), 5), "event_mean_net": round(float(y["n"].mean()), 5),
                "gross": {k: _slim(HI.spread_stats(g, lo, hi)) for k, (lo, hi) in splits.items()},
                "net": {k: _slim(HI.spread_stats(n, lo, hi)) for k, (lo, hi) in splits.items()}}
    return out


def _slim(st: dict) -> dict:
    keep = ("n_months", "mean_monthly", "t_blocks", "mde_monthly", "years_positive")
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in st.items() if k in keep}


def run_hi52(decl: dict) -> dict:
    for r, h in decl["input_sha256"].items():
        now = file_sha(REPO / decl["inputs"][r])
        if now != h:
            return {"verdict": "REFUSED", "reason": f"input {r} changed since the declaration ({h[:12]} -> {str(now)[:12]})"}
    res, prim = {}, None
    for r, rel in decl["inputs"].items():
        S = pd.read_parquet(REPO / rel)
        if "date" in S.columns and not isinstance(S.index, pd.DatetimeIndex):
            S = S.set_index("date")
        cols = {}
        for col in decl["reported"]:
            rd = read_series(S[col], decl["splits"], decl["sign"], decl["min_effect"])
            cols[col] = {"verdict": rd["verdict"], "reason": rd["reason"],
                         "stats": {k: _slim(v) for k, v in rd["stats"].items()},
                         "by_hold_year": rd["stats"]["full"].get("by_year"), "loo_worst": rd["loo_worst"]}
            if r == "hi52" and col == "fair_twin_net":
                prim = rd
        res[r] = cols
    return {"verdict": prim["verdict"], "reason": prim["reason"], "powered": prim.get("powered"),
            "primary": "hi52.fair_twin_net",
            "primary_stats": {k: _slim(v) for k, v in prim["stats"].items()},
            "primary_by_hold_year": prim["stats"]["full"].get("by_year"), "primary_loo_worst": prim["loo_worst"],
            "rules": res}


def run_insider_hold(decl: dict, run: str) -> dict:
    t0 = time.time()
    B, S = _insider_frames()
    E = insider_hold_events(B, S)
    del B, S
    gc.collect()
    E = E[(E["gate"] >= "2006-01-01") & (E["gate"] <= "2024-09-30")].reset_index(drop=True)
    E["eid"] = np.arange(len(E))
    say(f"  {len(E):,} events ({int(E['hold'].sum()):,} HOLD) {time.time() - t0:.0f}s")
    F = event_returns(E[["eid", "permno", "gate", "hold", "n_buyers"]], decl["horizons"], range(2006, 2025))
    F.to_parquet(OUT / f"theory_insider_hold_events_{run}.parquet")
    splits = decl["splits"]
    cells = {**_cohort_cells(F[F["hold"]], splits, decl["horizons"], "HOLD"),
             **_cohort_cells(F[~F["hold"]], splits, decl["horizons"], "SOLD")}
    y = F[F["H"] == 63].copy()
    y["n"] = y["r"] - y["r_band"] - y["rt"]
    prim = read_series(monthly(y[y["hold"]], "n"), splits, decl["sign"], decl["min_effect"])
    y["g"] = y["r"] - y["r_band"]
    diff = (monthly(y[y["hold"]], "g") - monthly(y[~y["hold"]], "g")).dropna()
    sep = read_series(diff, splits, "+1", decl["min_effect"])
    return {"verdict": prim["verdict"], "reason": prim["reason"], "powered": prim.get("powered"),
            "primary": "HOLD H63 net vs size band",
            "primary_stats": {k: _slim(v) for k, v in prim["stats"].items()},
            "primary_by_hold_year": prim["stats"]["full"].get("by_year"), "primary_loo_worst": prim["loo_worst"],
            "hold_minus_sold_gross_H63": {"verdict_if_primary": sep["verdict"], "reason": sep["reason"],
                                          "stats": {k: _slim(v) for k, v in sep["stats"].items()},
                                          "by_hold_year": sep["stats"]["full"].get("by_year")},
            "n_events": int(len(E)), "n_hold": int(E["hold"].sum()),
            "events_by_year": E["gate"].dt.year.value_counts().sort_index().astype(int).to_dict(),
            "hold_share_by_year": E.groupby(E["gate"].dt.year)["hold"].mean().round(3).to_dict(),
            "cells": cells, "seconds": round(time.time() - t0, 1)}


def run_beat_streak(decl: dict, run: str) -> dict:
    from backend.services import crsp_event_bridge as CEB  # noqa: PLC0415
    t0 = time.time()
    Q = pd.read_parquet(SURP, columns=["ticker", "measure", "fiscalp", "pyear", "pmon", "usfirm", "anndats",
                                       "actual", "surpmean"],
                        filters=[("measure", "=", "EPS"), ("fiscalp", "=", "QTR")])
    Q = Q[Q["usfirm"].astype(float) == 1]
    Q["anndats"] = pd.to_datetime(Q["anndats"], errors="coerce")
    Q = beat_streaks(Q)
    Q = Q[(Q["anndats"] >= "1993-06-01") & (Q["anndats"] <= "2024-09-30")]
    link = pd.read_parquet(IBLINK)
    Q["day"] = Q["anndats"].dt.normalize()
    Q, meta = CEB.link_permno(Q, link, ticker_col="ticker", day_col="day")
    Q["gate"] = Q["day"] + pd.offsets.BDay(1)
    Q["rday"] = Q["day"]
    Q = Q.drop_duplicates(["permno", "day"]).reset_index(drop=True)
    Q["eid"] = np.arange(len(Q))
    say(f"  {len(Q):,} linked announcements ({meta}) {time.time() - t0:.0f}s")
    F = event_returns(Q[["eid", "permno", "gate", "rday", "streak", "beat"]], decl["horizons"],
                      range(1993, 2025), reaction=True)
    F.to_parquet(OUT / f"theory_beat_streak_events_{run}.parquet")
    F["bucket"] = streak_bucket(F["streak"])
    splits = {**decl["splits"], "full": (None, None)}
    by_bucket = {}
    for H in decl["horizons"]:
        y = F[F["H"] == H].copy()
        y["g"] = y["r"] - y["r_band"]
        y["n"] = y["g"] - y["rt"]
        for k, (lo, hi) in splits.items():
            w = y
            if lo:
                w = w[w["entry"] >= lo]
            if hi:
                w = w[w["entry"] <= hi]
            tab = w.groupby("bucket").agg(n=("g", "size"), drift_gross=("g", "mean"), drift_net=("n", "mean"),
                                          car=("car", "mean"), rt_bps=("rt", lambda s: s.mean() * 1e4))
            by_bucket[f"H{H}_{k}"] = {b: {c: (round(float(v), 5) if c != "n" else int(v)) for c, v in r.items()}
                                      for b, r in tab.iterrows()}
    y = F[F["H"] == 63].copy()
    y["g"] = y["r"] - y["r_band"]
    diff = (monthly(y[y["streak"] >= 3], "g") - monthly(y[y["streak"] == 1], "g")).dropna()
    prim = read_series(diff, decl["splits"], decl["sign"], decl["min_effect"])
    trade = _cohort_cells(F[F["streak"] >= 3], decl["splits"], decl["horizons"], "STREAK3P")
    first = _cohort_cells(F[F["streak"] == 1], decl["splits"], decl["horizons"], "STREAK1")
    return {"verdict": prim["verdict"], "reason": prim["reason"], "powered": prim.get("powered"),
            "primary": "(streak>=3 - streak==1) H63 gross drift vs size band, sign fixed by design",
            "sign_applied": prim["sign_applied"],
            "primary_stats": {k: _slim(v) for k, v in prim["stats"].items()},
            "primary_by_hold_year": prim["stats"]["full"].get("by_year"), "primary_loo_worst": prim["loo_worst"],
            "drift_by_streak": by_bucket, "cells": {**trade, **first},
            "n_announcements": int(len(Q)), "link": meta,
            "events_by_year": Q["day"].dt.year.value_counts().sort_index().astype(int).to_dict(),
            "streak_share": Q["streak"].clip(upper=5).value_counts(normalize=True).sort_index().round(4).to_dict(),
            "seconds": round(time.time() - t0, 1)}


def part_run(cell: str, run: str, *, ram_probe=free_gb, sleep=time.sleep) -> int:
    from backend.services import hyp_lab as L  # noqa: PLC0415
    if CELLS.get(cell, {}).get("declared_only"):
        say(f"REFUSED: {cell} is DECLARED ONLY (C16, 2026-10-07): no runner exists yet; its precursor "
            f"has no point-in-time history before the first agency-month snapshot")
        return 2
    dp = decl_path(cell, run)
    if not dp.exists():
        say(f"REFUSED: no declaration {dp.name}")
        return 2
    decl = json.loads(dp.read_text(encoding="utf-8"))
    rp = result_path(cell, run)
    ok, why = verify_declaration(decl)
    if not ok:
        say(f"REFUSED: {why}")
        _record(L, decl, rp, {"verdict": "REFUSED", "reason": why})
        return 2
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    ok, gb = wait_for_ram(probe=ram_probe, sleep=sleep)
    if not ok:
        why = f"free RAM {gb:.2f} GB < {MIN_FREE_GB} GB after {MAX_WAIT_S // 60} minutes of polling"
        say(f"REFUSED: {why}")
        _record(L, decl, rp, {"verdict": "REFUSED", "reason": why})
        return 3
    t0 = time.time()
    try:
        res = {"hi52": lambda: run_hi52(decl), "insider_hold": lambda: run_insider_hold(decl, run),
               "beat_streak": lambda: run_beat_streak(decl, run)}[cell]()
    except Exception as e:  # noqa: BLE001 -- a crashed cell is a REFUSED verdict, recorded with its reason
        res = {"verdict": "REFUSED", "reason": f"{type(e).__name__}: {str(e)[:300]}"}
    res["free_ram_gb_at_start"] = round(gb, 2)
    res["wall_s"] = round(time.time() - t0, 1)
    _record(L, decl, rp, res)
    say(f"-> {rp.name}: {res['verdict']} ({res.get('reason')})")
    return 0


def _record(L, decl: dict, rp: Path, res: dict) -> None:
    doc = {"schema": "hyp_lab/theory_cell_results/1", "cell": decl.get("cell"), "run": decl.get("run"),
           "declaration_sha256": decl.get("sha256"), "hyp_id": decl.get("hyp_id"), "written_utc": _now(),
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decision": DECISION, "result": res}
    if rp.exists():
        rp = rp.with_name(rp.stem + f"_REFUSED_{datetime.now(timezone.utc).strftime('%H%M%S')}.json")
    _write_new(rp, doc)
    v = res.get("verdict") if res.get("verdict") in L.VERDICTS else "REFUSED"
    if decl.get("hyp_id") and decl["hyp_id"] in L.load_state():
        ps = res.get("primary_stats") or {}
        L.update(decl["hyp_id"], status="RUN", verdict=v, receipt=L._rel(rp),
                 fields={"reread_of": decl["reread_of"]} if decl.get("reread_of") else None,
                 summary={"verdict": v, "reason": res.get("reason"), "powered": bool(res.get("powered")),
                          "design": {"mean": (ps.get("design") or {}).get("mean_monthly"),
                                     "t": (ps.get("design") or {}).get("t_blocks")},
                          "confirm": {"mean": ((res.get("primary_stats") or {}).get("validate") or {}).get("mean_monthly"),
                                      "t": ((res.get("primary_stats") or {}).get("validate") or {}).get("t_blocks"),
                                      "mde": ((res.get("primary_stats") or {}).get("validate") or {}).get("mde_monthly")}})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cell", required=True, choices=sorted(CELLS))
    ap.add_argument("--part", required=True, choices=["declare", "run"])
    ap.add_argument("--run", default="")
    a = ap.parse_args(argv)
    run = a.run or f"TC_{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')}"
    if a.part == "declare":
        return part_declare(a.cell, run)
    return part_run(a.cell, run)


if __name__ == "__main__":
    raise SystemExit(main())
