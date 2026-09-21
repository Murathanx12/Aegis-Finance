"""J1 -- THE ERROR DATASET: one row per graded forecast and per decision, with
the reason it was wrong named by a RULE rather than by a model.

WHY THIS EXISTS
===============
The ledger holds 24,839 forecasts and (as of 2026-09-21) 14,703 graded ones,
and the only thing anybody ever read off them was an aggregate Brier. An
aggregate says the programme is badly calibrated; it never says WHICH WAY, and
"which way" is the whole content of a curriculum. A forecast that called the
sign right and the size wrong is a different repair from one that called the
sign wrong, which is a different repair again from one whose gross edge was
real and whose net edge the cost model ate.

So every graded row gets a CLUSTER, and every cluster is a RULE -- readable,
testable, and free. No model is asked anything here; `llm_spend_usd` is 0.0 by
construction because there is no call site.

THE PRECEDENCE IS DECLARED, NOT EMERGENT
========================================
A row can satisfy several rules at once (a p=0.8 call that was wrong AND right
at the neighbouring horizon). Picking "the first one that matched" without
saying the order is how a cluster count becomes an artefact of statement order,
so `CLUSTER_PRECEDENCE` is the order, it is on the receipt, and every row also
carries `cluster_candidates` -- every rule that fired -- so a reader can re-cut
the population under a different precedence without re-running anything.

THE RESIDUAL IS NAMED
=====================
The task's vocabulary has nine clusters and all nine are errors or near-misses.
A right, unremarkable forecast matches none of them, and a row that matches
nothing is a row that silently leaves the dataset. `CORRECT_UNREMARKABLE` is
the declared residual, counted like any other cluster, and `UNGRADEABLE` always
carries `ungradeable_reason`: nothing is dropped, ever.

Licence: PRODUCT_EXPERIMENT. Reads two ledgers and one local bar parquet;
writes one JSONL and one receipt. It places no order and moves no capital.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config                                          # noqa: E402

JOB = "J1_error_dataset"
LICENCE = "PRODUCT_EXPERIMENT"
STAGE = "pnl"

#: The benchmark every row is measured against. SPY is in the local bar panel
#: (`paper_books.load_bars()`); a row whose window SPY cannot cover says so by
#: name rather than reporting an excess computed against nothing.
BENCHMARK = "SPY"

#: The horizons the ledger actually uses, ascending. `RIGHT_THESIS_WRONG_HORIZON`
#: only ever looks at the IMMEDIATE neighbours of a row's own horizon in this
#: list -- not at "any horizon that would have worked", which is a different and
#: much weaker claim.
HORIZON_GRID = (1, 2, 5, 20, 60, 120, 252)

#: Observables whose call is a DIRECTION (a sign claim about the return or the
#: excess). Everything else is a MAGNITUDE claim, and a magnitude miss is not a
#: direction miss -- conflating them is how "we keep getting the direction
#: wrong" gets said about a ledger that is 40% threshold questions.
DIRECTIONAL_OBSERVABLES = ("return_sign", "beats_benchmark")
MAGNITUDE_OBSERVABLES = ("abs_move_exceeds", "drawdown_exceeds")

CLUSTERS = (
    "UNGRADEABLE",
    "REFUSED_THEN_PERFORMED",
    "EXPLORE_DESERVED_MORE",
    "COSTS_KILLED_EDGE",
    "RIGHT_THESIS_WRONG_HORIZON",
    "HIGH_CONFIDENCE_WRONG",
    "WRONG_DIRECTION",
    "RIGHT_DIRECTION_WRONG_MAGNITUDE",
    "LOW_CONFIDENCE_RIGHT",
    "CORRECT_UNREMARKABLE",
)

#: First match wins. Declared here, printed on the receipt, and every row keeps
#: the full candidate list so this order is auditable rather than load-bearing.
CLUSTER_PRECEDENCE = CLUSTERS

#: One sentence per cluster naming the experiment it justifies. The curriculum
#: block is these sentences, ranked by (count x mean |error|) -- so the top item
#: is the repair with the most total error behind it, not the loudest one.
CURRICULUM_EXPERIMENT = {
    "WRONG_DIRECTION": (
        "Split the sign misses by mechanism and re-ask whether the mechanism "
        "has ANY directional content: a mechanism whose sign accuracy is 0.5 "
        "on its own graded rows should be reduced to a magnitude/volatility "
        "forecaster rather than repaired as a direction forecaster."),
    "RIGHT_DIRECTION_WRONG_MAGNITUDE": (
        "Re-grade the threshold observables against the REALISED distribution "
        "of |return| at that horizon: if the calls are biased one way, the "
        "threshold prior is wrong and it is a constant, not a model."),
    "RIGHT_THESIS_WRONG_HORIZON": (
        "Re-issue this mechanism's forecasts at the neighbouring horizon that "
        "was right and grade the pair: if the shifted horizon wins on the same "
        "cases, the mechanism's horizon is mis-specified, not its thesis."),
    "COSTS_KILLED_EDGE": (
        "Price the mechanism's whole graded population at the declared round "
        "trip and report gross and net side by side: a mechanism whose edge "
        "only exists gross is a turnover problem, testable by holding longer."),
    "HIGH_CONFIDENCE_WRONG": (
        "Fit a monotone recalibration on the p>=0.70 bucket alone and test it "
        "out of sample: an over-confident tail is the cheapest calibration "
        "repair there is, and it needs no new signal."),
    "LOW_CONFIDENCE_RIGHT": (
        "Test whether the p<=0.55 rows carry usable information the sizing "
        "throws away -- a mechanism that is right at 0.52 more often than 52% "
        "is under-confident, and under-confidence costs size, not accuracy."),
    "REFUSED_THEN_PERFORMED": (
        "Run the refusal classes as a PROBE population against their own "
        "matched controls: a refusal class whose names outperform is a gate "
        "that is costing money, and its sentence is the hypothesis."),
    "EXPLORE_DESERVED_MORE": (
        "Raise the explore budget for the signals whose EXPLORE names cleared "
        "the bar and re-draw: a Thompson arm that keeps paying is an arm whose "
        "posterior is being under-updated."),
    "UNGRADEABLE": (
        "Fix the named grading gap first: an ungradeable row is a forecast "
        "already paid for and never read, and it is the only cluster whose "
        "repair costs nothing but plumbing."),
    "CORRECT_UNREMARKABLE": (
        "No experiment: this is the residual of rows that were right and "
        "carried no notable error. It is on the receipt so the counts sum."),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir() -> Path:
    return REPO / "backend" / "data" / "optimus"


def run_date() -> str:
    return datetime.now().date().isoformat()


def out_dir(day: str | None = None) -> Path:
    return data_dir() / f"night_factory_{day or run_date()}"


# ===========================================================================
# THE PRICE PANEL, as plain numpy -- 14,703 rows x several window lookups is
# minutes in pandas .loc and seconds in searchsorted.
# ===========================================================================


class Panel:
    """Sorted (dates, closes) per symbol, with window returns by searchsorted."""

    def __init__(self, by_symbol: dict):
        self._s = by_symbol

    @classmethod
    def from_bars(cls, bars) -> "Panel":
        import numpy as np

        out: dict = {}
        b = bars[["symbol", "date", "close"]].dropna()
        b = b.sort_values(["symbol", "date"])
        sym = b["symbol"].to_numpy()
        dt = b["date"].to_numpy()
        cl = b["close"].to_numpy(dtype="float64")
        if len(sym):
            edges = np.flatnonzero(sym[1:] != sym[:-1]) + 1
            starts = np.concatenate([[0], edges])
            ends = np.concatenate([edges, [len(sym)]])
            for i, j in zip(starts, ends):
                out[str(sym[i])] = (dt[i:j], cl[i:j])
        return cls(out)

    @classmethod
    def local(cls) -> "Panel":
        from backend.services import paper_books as PB
        return cls.from_bars(PB.load_bars())

    @property
    def symbols(self) -> list[str]:
        return sorted(self._s)

    def has(self, symbol: str) -> bool:
        return symbol in self._s

    def window(self, symbol: str, start: str, horizon: int):
        """(start_date, end_date, return) over `horizon` bars from `start`.

        None when the symbol is absent or the panel has fewer than
        `horizon + 1` bars from `start` -- the same window rule
        `belief_state.resolve_one` grades under, so a row this returns None for
        is a row the resolver would also refuse.
        """
        import numpy as np

        hit = self._s.get(symbol)
        if hit is None:
            return None
        dates, closes = hit
        i = int(np.searchsorted(dates, np.datetime64(str(start)[:10]), side="left"))
        j = i + int(horizon)
        if i >= len(dates) or j >= len(dates):
            return None
        c0, c1 = float(closes[i]), float(closes[j])
        if c0 <= 0:
            return None
        return (str(dates[i])[:10], str(dates[j])[:10], c1 / c0 - 1.0)

    def between(self, symbol: str, start_date: str, end_date: str):
        """Return of `symbol` between two CALENDAR dates, on its own bars."""
        import numpy as np

        hit = self._s.get(symbol)
        if hit is None:
            return None
        dates, closes = hit
        i = int(np.searchsorted(dates, np.datetime64(str(start_date)[:10]), side="left"))
        j = int(np.searchsorted(dates, np.datetime64(str(end_date)[:10]), side="right")) - 1
        if i >= len(dates) or j <= i or j >= len(dates):
            return None
        c0, c1 = float(closes[i]), float(closes[j])
        if c0 <= 0:
            return None
        return c1 / c0 - 1.0


# ===========================================================================
# THE RULES
# ===========================================================================


def neighbours(horizon: int) -> tuple[int, ...]:
    """The immediate neighbours of `horizon` in the declared grid."""
    grid = list(HORIZON_GRID)
    if horizon not in grid:
        lower = [h for h in grid if h < horizon]
        upper = [h for h in grid if h > horizon]
        return tuple([lower[-1]] if lower else []) + tuple([upper[0]] if upper else [])
    k = grid.index(horizon)
    out = []
    if k > 0:
        out.append(grid[k - 1])
    if k + 1 < len(grid):
        out.append(grid[k + 1])
    return tuple(out)


def cluster_candidates(row: dict) -> list[str]:
    """Every rule that fires on `row`. Order is NOT precedence."""
    if row.get("ungradeable_reason"):
        return ["UNGRADEABLE"]

    hits: list[str] = []
    excess = row.get("excess_return")
    direction = row.get("decision")
    authority = row.get("authority")
    hi = float(config.J1_EXCESS_PERFORMED_PCT) / 100.0

    if excess is not None and float(excess) >= hi:
        if direction in ("REFUSED", "PROBE"):
            hits.append("REFUSED_THEN_PERFORMED")
        if authority == "EXPLORE":
            hits.append("EXPLORE_DESERVED_MORE")

    p = row.get("expected")
    right = row.get("right")
    gross = row.get("gross_return")
    net = row.get("net_return")
    if gross is not None and net is not None and float(gross) > 0 and float(net) <= 0:
        hits.append("COSTS_KILLED_EDGE")
    if row.get("right_at_neighbour_horizon"):
        hits.append("RIGHT_THESIS_WRONG_HORIZON")
    if p is not None and right is False and float(p) >= config.J1_HIGH_CONFIDENCE_P:
        hits.append("HIGH_CONFIDENCE_WRONG")
    if right is False and row.get("observable") in DIRECTIONAL_OBSERVABLES:
        hits.append("WRONG_DIRECTION")
    if right is False and row.get("observable") in MAGNITUDE_OBSERVABLES:
        hits.append("RIGHT_DIRECTION_WRONG_MAGNITUDE")
    if p is not None and right is True and float(p) <= config.J1_LOW_CONFIDENCE_P:
        hits.append("LOW_CONFIDENCE_RIGHT")
    if not hits:
        hits.append("CORRECT_UNREMARKABLE")
    return hits


def cluster_of(row: dict) -> tuple[str, list[str]]:
    hits = cluster_candidates(row)
    for c in CLUSTER_PRECEDENCE:
        if c in hits:
            return c, hits
    return "CORRECT_UNREMARKABLE", hits


# ===========================================================================
# ROW BUILDERS
# ===========================================================================


def _cost_round_trip() -> float:
    return 2.0 * float(config.J1_COST_BPS_PER_SIDE) / 1e4


def prediction_row(rec: dict, panel: Panel) -> dict:
    """One error-dataset row from one ledger record."""
    tkr = str(rec.get("ticker") or "")
    horizon = int(rec.get("horizon_days") or 0)
    made = str(rec.get("made_at") or "")[:10]
    obs = str(rec.get("observable") or "")
    p = rec.get("probability")
    p = float(p) if p is not None else None
    outcome = rec.get("outcome")
    detail = rec.get("resolution_detail") or {}

    row: dict = {
        "source": "prediction",
        "row_id": rec.get("prediction_id"),
        "ticker": tkr,
        "mechanism": str(rec.get("mechanism_id") or rec.get("specialist") or "UNATTRIBUTED"),
        "observable": obs,
        "horizon_days": horizon,
        "information_cutoff": rec.get("made_at"),
        "decision": f"P({obs})={p}" if p is not None else obs,
        "expected": p,
        "expected_outcome": None if p is None else int(p >= 0.5),
        "actual_outcome": None if outcome is None else int(outcome),
        "actual_return": detail.get("realised_return"),
        "benchmark_return": None,
        "excess_return": None,
        "gross_return": None,
        "net_return": None,
        "forecast_error": None,
        "abs_error": None,
        "brier": rec.get("brier"),
        "calibration_bucket": rec.get("calibration_bucket"),
        "falsifier": None,
        "falsifier_fired": None,
        "right": None,
        "right_at_neighbour_horizon": None,
        "neighbour_horizons_checked": [],
        "authority": None,
        "ungradeable_reason": None,
    }

    if rec.get("void_reason"):
        row["ungradeable_reason"] = f"VOID: {rec['void_reason']}"
    elif outcome is None or not rec.get("resolved_at"):
        row["ungradeable_reason"] = (
            "NOT_GRADED: the ledger carries no outcome for this record "
            f"(resolves_after {rec.get('resolves_after')})")
    elif p is None:
        row["ungradeable_reason"] = (
            "NO_PROBABILITY: the record declares no forecast probability")
    if row["ungradeable_reason"]:
        row["cluster"], row["cluster_candidates"] = cluster_of(row)
        return row

    called = int(p >= 0.5)
    right = bool(called == int(outcome))
    row["right"] = right
    row["forecast_error"] = float(p - int(outcome))
    row["abs_error"] = abs(row["forecast_error"])

    w = panel.window(tkr, made, horizon) if horizon > 0 else None
    if w is not None:
        d0, d1, ret = w
        row["window"] = [d0, d1]
        if row["actual_return"] is None:
            row["actual_return"] = ret
        b = panel.between(BENCHMARK, d0, d1)
        if b is None:
            row["benchmark_note"] = (
                f"CANNOT DETERMINE: {BENCHMARK} has no bars covering {d0}..{d1}")
        else:
            row["benchmark_return"] = b
            row["excess_return"] = float(ret - b)
        if obs in DIRECTIONAL_OBSERVABLES:
            base = row["excess_return"] if obs == "beats_benchmark" else ret
            if base is not None:
                g = float(base if called == 1 else -base)
                row["gross_return"] = g
                row["net_return"] = float(g - _cost_round_trip())
        if obs in DIRECTIONAL_OBSERVABLES and not right:
            checked, hit = [], False
            for h in neighbours(horizon):
                w2 = panel.window(tkr, made, h)
                if w2 is None:
                    continue
                d0b, d1b, r2 = w2
                if obs == "beats_benchmark":
                    b2 = panel.between(BENCHMARK, d0b, d1b)
                    if b2 is None:
                        continue
                    r2 = r2 - b2
                checked.append(h)
                if int(r2 > 0) == called:
                    hit = True
            row["neighbour_horizons_checked"] = checked
            row["right_at_neighbour_horizon"] = hit if checked else None
    else:
        row["benchmark_note"] = (
            f"CANNOT DETERMINE: the local panel has no {horizon + 1}-bar window "
            f"for {tkr} from {made}; the row is graded by the ledger, the "
            f"benchmark comparison is not")

    row["cluster"], row["cluster_candidates"] = cluster_of(row)
    return row


def decision_row(rec: dict, panel: Panel, *, today: str) -> dict:
    """One error-dataset row from one decision-contract row."""
    tkr = str(rec.get("ticker") or "")
    hz = rec.get("horizon") or {}
    sessions = hz.get("sessions") if isinstance(hz, dict) else None
    if sessions is None and isinstance(hz, dict) and hz.get("months") is not None:
        sessions = int(round(float(hz["months"]) * 21))
    sessions = int(sessions or 0)
    asof = str(rec.get("asof") or today)[:10]

    row: dict = {
        "source": "decision",
        "row_id": rec.get("decision_id"),
        "ticker": tkr,
        "mechanism": str(rec.get("signal") or rec.get("source") or "UNATTRIBUTED"),
        "observable": "decision_excess",
        "horizon_days": sessions,
        "information_cutoff": rec.get("information_cutoff_utc"),
        "decision": rec.get("direction"),
        "authority": rec.get("authority"),
        "hypothesis_id": rec.get("hypothesis_id"),
        "selection_probability": rec.get("selection_probability"),
        "expiry_utc": rec.get("expiry_utc"),
        "expected": None,
        "expected_outcome": None,
        "actual_outcome": None,
        "actual_return": None,
        "benchmark_return": None,
        "excess_return": None,
        "gross_return": None,
        "net_return": None,
        "forecast_error": None,
        "abs_error": None,
        "brier": None,
        "calibration_bucket": None,
        "falsifier": rec.get("falsifier"),
        "falsifier_fired": (None if rec.get("falsifier_status") in (None, "NONE_SET")
                            else rec.get("falsifier_status") == "FIRED"),
        "right": None,
        "right_at_neighbour_horizon": None,
        "neighbour_horizons_checked": [],
        "ungradeable_reason": None,
    }

    w = panel.window(tkr, asof, sessions) if sessions > 0 else None
    if sessions <= 0:
        row["ungradeable_reason"] = (
            "NO_HORIZON: the decision row declares no horizon in sessions")
    elif w is None:
        row["ungradeable_reason"] = (
            f"WINDOW_NOT_CLOSED: the local panel has no {sessions + 1}-bar window for "
            f"{tkr} from {asof} -- the decision's horizon has not elapsed on the bars "
            f"this machine holds")
    else:
        d0, d1, ret = w
        row["window"] = [d0, d1]
        row["actual_return"] = ret
        b = panel.between(BENCHMARK, d0, d1)
        if b is None:
            row["ungradeable_reason"] = (
                f"NO_BENCHMARK: {BENCHMARK} has no bars covering {d0}..{d1}")
        else:
            row["benchmark_return"] = b
            row["excess_return"] = float(ret - b)
            row["actual_outcome"] = int(row["excess_return"] > 0)
            if rec.get("direction") == "BUY":
                row["right"] = bool(row["excess_return"] > 0)
                row["gross_return"] = row["excess_return"]
                row["net_return"] = float(row["excess_return"] - _cost_round_trip())
                row["forecast_error"] = float(row["excess_return"])
                row["abs_error"] = abs(row["excess_return"])

    row["cluster"], row["cluster_candidates"] = cluster_of(row)
    return row


# ===========================================================================
# AGGREGATION
# ===========================================================================


def brier_vs_climatology(rows: list[dict]) -> dict:
    """Mean Brier of the graded rows against the base-rate forecaster.

    Climatology is the base rate of `outcome == 1` IN THE SAME POPULATION, per
    observable and overall. Skill is `1 - brier / brier_climatology`; a negative
    skill means the ledger would be better off saying the base rate every time,
    which is a fact worth printing in one number.
    """
    graded = [r for r in rows if r.get("brier") is not None
              and r.get("actual_outcome") is not None]
    by_obs: dict = {}
    for r in graded:
        by_obs.setdefault(r.get("observable") or "UNKNOWN", []).append(r)

    def block(rs: list[dict]) -> dict:
        if not rs:
            return {"n": 0, "brier": None, "climatology_p": None,
                    "brier_climatology": None, "skill": None}
        n = len(rs)
        base = sum(int(r["actual_outcome"]) for r in rs) / n
        br = sum(float(r["brier"]) for r in rs) / n
        bc = sum((base - int(r["actual_outcome"])) ** 2 for r in rs) / n
        return {"n": n, "brier": round(br, 6), "climatology_p": round(base, 6),
                "brier_climatology": round(bc, 6),
                "skill": (None if bc == 0 else round(1.0 - br / bc, 6))}

    return {"overall": block(graded),
            "by_observable": {k: block(v) for k, v in sorted(by_obs.items())},
            "definition": ("climatology = the base rate of outcome==1 in the same "
                           "population; skill = 1 - brier / brier_climatology")}


def _counts(rows: list[dict], key) -> dict:
    out: dict = {}
    for r in rows:
        k = str(key(r))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


#: The declared residual is NOT a curriculum item: it has no experiment, and a
#: top-5 slot spent saying "no experiment" is a slot not spent on a repair. It
#: is still counted in `counts_by_cluster`, and the receipt names the exclusion.
CURRICULUM_EXCLUDED = ("CORRECT_UNREMARKABLE",)


def curriculum(rows: list[dict]) -> list[dict]:
    """The top 5 clusters by (count x mean |error|), each with its experiment."""
    agg: dict = {}
    for r in rows:
        c = r["cluster"]
        a = agg.setdefault(c, {"count": 0, "abs_error_sum": 0.0, "n_with_error": 0})
        a["count"] += 1
        e = r.get("abs_error")
        if e is not None:
            a["abs_error_sum"] += abs(float(e))
            a["n_with_error"] += 1
    out = []
    for c, a in agg.items():
        if c in CURRICULUM_EXCLUDED:
            continue
        mean_err = (a["abs_error_sum"] / a["n_with_error"]) if a["n_with_error"] else 0.0
        out.append({
            "cluster": c,
            "count": a["count"],
            "n_with_measured_error": a["n_with_error"],
            "mean_abs_error": round(mean_err, 6),
            "priority": round(a["count"] * mean_err, 4),
            "experiment": CURRICULUM_EXPERIMENT.get(c, "no experiment declared"),
        })
    out.sort(key=lambda d: (-d["priority"], d["cluster"]))
    return out[:5]


def largest_errors(rows: list[dict], n: int = 20) -> list[dict]:
    scored = [r for r in rows if r.get("abs_error") is not None]
    scored.sort(key=lambda r: (-float(r["abs_error"]), str(r.get("row_id"))))
    return [{"ticker": r["ticker"], "date": str(r.get("information_cutoff"))[:10],
             "mechanism": r["mechanism"], "expected": r.get("expected"),
             "actual": r.get("actual_outcome"),
             "actual_return": (None if r.get("actual_return") is None
                               else round(float(r["actual_return"]), 6)),
             "excess_return": (None if r.get("excess_return") is None
                               else round(float(r["excess_return"]), 6)),
             "abs_error": round(float(r["abs_error"]), 6),
             "cluster": r["cluster"]}
            for r in scored[:n]]


# ===========================================================================
# THE RUN
# ===========================================================================


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def decision_rows_on_disk(dec_dir: Path) -> list[dict]:
    """Every row of every decision DAY file.

    The ledger is a STATE LOG, not the rows; reading only `ledger.jsonl` would
    report 86 state transitions as the whole decision population.
    """
    rows: list[dict] = []
    dec_dir = Path(dec_dir)
    if not dec_dir.is_dir():
        return rows
    for f in sorted(dec_dir.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for r in (payload.get("rows") or []):
            if not isinstance(r, dict):
                continue
            r = dict(r)
            r.setdefault("asof", payload.get("date"))
            rows.append(r)
    return rows


def ledger_states(dec_dir: Path) -> dict:
    """State counts off `decisions/ledger.jsonl`, for the receipt."""
    return _counts(read_jsonl(Path(dec_dir) / "ledger.jsonl"),
                   lambda r: r.get("state") or "UNKNOWN")


def build(*, predictions: Path, decisions_dir: Path, panel: Panel,
          limit: int | None = None, today: str | None = None) -> tuple[list[dict], dict]:
    today = today or run_date()
    recs = read_jsonl(predictions)
    if limit:
        recs = recs[-int(limit):]
    rows = [prediction_row(r, panel) for r in recs]
    drows = decision_rows_on_disk(decisions_dir)
    rows += [decision_row(r, panel, today=today) for r in drows]
    meta = {"n_prediction_records": len(recs), "n_decision_rows": len(drows)}
    return rows, meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="J1 -- the error dataset")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--seed", type=int, default=20260921,
                    help="accepted for interface parity; nothing here is random")
    ap.add_argument("--resume", action="store_true",
                    help="tolerated: this job rebuilds the dataset in one pass")
    ap.add_argument("--smoke", action="store_true",
                    help="the last 500 ledger records only")
    ap.add_argument("--date", default=None)
    ap.add_argument("--rows-out", default=None)
    ap.add_argument("--stage", default=STAGE)
    args = ap.parse_args(argv)

    t0 = time.time()
    day = args.date or run_date()
    folder = out_dir(day)
    out = Path(args.out) if args.out else (
        folder / f"{JOB}_run{args.run:02d}{'_smoke' if args.smoke else ''}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows_path = (Path(args.rows_out) if args.rows_out
                 else out.parent / "J1_error_dataset_rows.jsonl")

    predictions = data_dir() / "predictions.jsonl"
    decisions_dir = data_dir() / "decisions"

    receipt: dict = {
        "job": JOB, "licence": LICENCE, "stage": args.stage, "llm_spend_usd": 0.0,
        "run": args.run, "smoke": bool(args.smoke), "date": day,
        "question": ("Of every graded forecast and decision this programme has made, "
                     "WHICH WAY was it wrong, how much error sits behind each way, "
                     "and what experiment does the biggest pile justify?"),
        "method": {
            "clusters": list(CLUSTERS),
            "precedence": list(CLUSTER_PRECEDENCE),
            "precedence_note": ("first match wins; every row also carries "
                                "`cluster_candidates` -- every rule that fired -- so "
                                "the population can be re-cut without re-running"),
            "benchmark": BENCHMARK,
            "cost_round_trip_bps": 2.0 * float(config.J1_COST_BPS_PER_SIDE),
            "cost_source": ("config.J1_COST_BPS_PER_SIDE, pinned equal to "
                            "night_g3_evolve_v2.COST_BPS by test"),
            "high_confidence_p": config.J1_HIGH_CONFIDENCE_P,
            "low_confidence_p": config.J1_LOW_CONFIDENCE_P,
            "performed_excess_pct": config.J1_EXCESS_PERFORMED_PCT,
            "horizon_grid": list(HORIZON_GRID),
            "llm": "NONE. There is no call site in this module.",
        },
        "inputs": {"predictions": str(predictions), "decisions_dir": str(decisions_dir)},
        "status": "running", "written_utc": _now(),
    }
    out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")

    try:
        panel = Panel.local()
        receipt["bars"] = {"available": True, "symbols": len(panel.symbols),
                           "benchmark_present": panel.has(BENCHMARK)}
    except Exception as exc:                                        # noqa: BLE001
        panel = Panel({})
        receipt["bars"] = {"available": False,
                           "reason": f"CANNOT DETERMINE: {type(exc).__name__}: {exc}"}

    rows, meta = build(predictions=predictions, decisions_dir=decisions_dir,
                       panel=panel, limit=500 if args.smoke else None, today=day)
    if not rows:
        receipt["status"] = "REFUSED"
        receipt["verdict"] = (f"REFUSED: no forecast and no decision row on disk "
                              f"({predictions}, {decisions_dir})")
        receipt["headline"] = receipt["verdict"]
        receipt["written_utc"] = _now()
        receipt["elapsed_s"] = round(time.time() - t0, 1)
        out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
        print(receipt["verdict"])
        return 2

    with rows_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")

    graded = [r for r in rows if not r.get("ungradeable_reason")]
    ung = [r for r in rows if r.get("ungradeable_reason")]
    receipt.update(meta)
    receipt["n_rows"] = len(rows)
    receipt["n_gradeable"] = len(graded)
    receipt["n_ungradeable"] = len(ung)
    receipt["counts_by_cluster"] = _counts(rows, lambda r: r["cluster"])
    receipt["counts_by_mechanism"] = _counts(rows, lambda r: r["mechanism"])
    receipt["counts_by_horizon"] = _counts(rows, lambda r: r["horizon_days"])
    receipt["counts_by_calibration_bucket"] = _counts(
        [r for r in rows if r.get("calibration_bucket")],
        lambda r: r["calibration_bucket"])
    receipt["ungradeable_reasons"] = _counts(
        ung, lambda r: str(r["ungradeable_reason"]).split(":")[0])
    receipt["decision_ledger_states"] = ledger_states(decisions_dir)
    receipt["falsifier"] = {
        "rows_with_a_falsifier": sum(1 for r in rows if r.get("falsifier")),
        "fired": sum(1 for r in rows if r.get("falsifier_fired") is True),
        "not_fired": sum(1 for r in rows if r.get("falsifier_fired") is False),
        "no_falsifier_declared": sum(1 for r in rows if r.get("falsifier_fired") is None),
    }
    receipt["brier"] = brier_vs_climatology(rows)
    receipt["largest_errors"] = largest_errors(rows, 20)
    receipt["curriculum"] = curriculum(rows)
    receipt["curriculum_excluded"] = {
        "clusters": list(CURRICULUM_EXCLUDED),
        "why": ("the declared residual carries no experiment; it is counted in "
                "counts_by_cluster and excluded from the ranked curriculum so a "
                "top-5 slot is not spent saying 'no experiment'"),
    }
    receipt["rows_path"] = str(rows_path)

    top = receipt["curriculum"][0] if receipt["curriculum"] else {}
    b = receipt["brier"]["overall"]
    biggest = max(receipt["counts_by_cluster"], key=receipt["counts_by_cluster"].get)
    head = (f"{len(rows)} error rows ({len(graded)} gradeable, {len(ung)} ungradeable "
            f"and every one carries its reason); biggest cluster {biggest} at "
            f"{receipt['counts_by_cluster'][biggest]}; Brier {b['brier']} vs "
            f"climatology {b['brier_climatology']} (skill {b['skill']}) on "
            f"{b['n']} graded rows")
    receipt["headline"] = head
    receipt["verdict"] = (
        (f"CURRICULUM: {top.get('cluster')} carries the most total error "
         f"({top.get('count')} rows x mean |error| {top.get('mean_abs_error')}). "
         f"{top.get('experiment')}")
        if top else "CANNOT DETERMINE: no cluster carried error")
    receipt["status"] = "done"
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = _now()
    out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print("\n" + head)
    print(receipt["verdict"])
    print(f"rows:    {rows_path}")
    print(f"receipt: {out}")
    return 0


def J1_error_dataset(smoke: bool = False, run: int = 1) -> dict:
    out = out_dir() / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = ["--run", str(run), "--out", str(out)] + (["--smoke"] if smoke else [])
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
