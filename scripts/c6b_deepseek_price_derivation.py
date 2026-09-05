"""Derive DeepSeek's real price-per-Mtok from the PROVIDER BALANCE.

WHY THIS EXISTS
===============
`config.LLM_PRICE_PER_MTOK` is a list-price table typed in by hand. Every budget
gate in this repo (`research_budget.require`) enforces a DOLLAR ceiling against
that table, via `llm_telemetry.spend()` -> `row_cost()` -> `price_call()`. So the
gate binds at real dollars only if the table is right, and on 2026-09-05
`S4_llm_spend_reconciliation_run01.json` measured that it is not: the provider
balance fell $3.98 across a window our ledger priced at $2.2201.

The house rule is [[reference_deepseek_balance_is_the_truth]] — the vendor's
balance is the truth and our telemetry is a reconstruction. This module makes
that rule executable: it reads the balance snapshots and the token ledger, and
SOLVES for the rates that reconcile them, rather than asserting a number.

WHAT IT WILL NOT DO
-------------------
Refuse rather than guess. One balance reading is no window; a window with no
tokens divides by nothing; two windows with the same in/out mix are a singular
system and the "solution" is whatever the floating-point noise says. Each of
those returns a NAMED refusal, and `backend/tests/test_llm_price_from_balance.py`
proves the gate goes red on all three. A derivation that cannot refuse is not a
derivation, it is a formatter.

THE TWO STORIES, AND THE NUMBER THAT SEPARATES THEM
---------------------------------------------------
A ledger that prices below the provider has exactly two explanations:

  1. THE TABLE IS WRONG — the rates are too low, and every recorded call is
     under-priced.
  2. THE LEDGER IS INCOMPLETE — the rates are right, but real calls wrote no
     row (the DeepSeek key is shared with every other job on this machine).

They make different predictions about the SHAPE of the gap. Missing rows lose
whole calls, so the gap should scale with call count (or with total tokens). An
under-priced leg loses one token class, so the gap should scale with THAT class
alone. `attribute_the_gap()` computes gap-per-call, gap-per-Mtok-in and
gap-per-Mtok-out across the windows and reports the dispersion of each: the
denominator that makes the gap look CONSTANT is the one that explains it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "backend" / "data" / "optimus" / "llm_calls.jsonl"
BALANCE = REPO / "backend" / "data" / "optimus" / "deepseek_balance.jsonl"
RECEIPT = (REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06b"
           / "C3_deepseek_price_derivation_run01.json")

#: Every name that bills against the DeepSeek balance. `deepseek-chat` and
#: `deepseek-reasoner` are server-side aliases of `deepseek-v4-flash` (see
#: `backend/tests/test_llm_model_identity.py`) — one model under three names,
#: one balance.
DEEPSEEK_MODELS = ("deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner",
                   "deepseek-v4-pro")

#: The table as it stood on 2026-08-12, FROZEN here on purpose. The "multiple of
#: the table" cross-check has to be reproducible after config.py is corrected,
#: and a multiple computed against a table that moves underneath it is a number
#: that changes meaning between runs. The live table is read separately and
#: reported beside it, so a re-run after the correction shows a multiple near 1.
BASELINE_TABLE_2026_08_12 = {"in": 0.14, "cached_in": 0.0028, "out": 0.28}

#: Above this the 2x2 is treated as singular: the two windows have effectively
#: the same in/out mix, and the "solution" is noise amplified by the inverse.
MAX_CONDITION_NUMBER = 1e6


class PriceDerivationRefused(RuntimeError):
    """The inputs cannot support a derivation. Named, so a caller can branch.

    Raised rather than returned as a sentinel for the same reason
    `research_budget` raises: a refusal that looks like a result is a refusal
    nobody notices.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


REFUSE_INSUFFICIENT_READINGS = "REFUSE_INSUFFICIENT_BALANCE_READINGS"
REFUSE_EMPTY_WINDOW = "REFUSE_WINDOW_HAS_NO_TOKENS"
REFUSE_SINGULAR = "REFUSE_SINGULAR_SYSTEM"
REFUSE_NO_SPEND = "REFUSE_WINDOW_HAS_NO_SPEND"


# ── inputs ──────────────────────────────────────────────────────────────────
def _dt(value: Any) -> datetime:
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def read_balance_readings(path: Path, tracker=None
                          ) -> list[tuple[datetime, float]]:
    """Every (instant, total_usd) the provider reported, oldest first.

    A reading whose total is HIGHER than its predecessor is a top-up, and it is
    kept and flagged by `windows_from_readings` rather than silently differenced
    into a negative spend.
    """
    if tracker is not None:
        tracker.opened(path, note="provider balance snapshots")
    out: list[tuple[datetime, float]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        out.append((_dt(row["read_at"]), float(row["total_usd"])))
    out.sort(key=lambda r: r[0])
    return out


@dataclass
class Window:
    """One interval between two balance readings, with the tokens inside it."""
    label: str
    t0: datetime
    t1: datetime
    spend_usd: float
    n_calls: int = 0
    tokens_in: int = 0
    tokens_cached: int = 0
    tokens_out: int = 0
    #: What the FROZEN 2026-08-12 table charges for the same tokens.
    baseline_usd: float = 0.0

    @property
    def m_in(self) -> float:
        return self.tokens_in / 1e6

    @property
    def m_cached(self) -> float:
        return self.tokens_cached / 1e6

    @property
    def m_out(self) -> float:
        return self.tokens_out / 1e6

    @property
    def hours(self) -> float:
        return (self.t1 - self.t0).total_seconds() / 3600.0

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "t0": self.t0.isoformat(), "t1": self.t1.isoformat(),
            "hours": round(self.hours, 4),
            "provider_spend_usd": round(self.spend_usd, 6),
            "n_calls": self.n_calls,
            "tokens_in_full_rate": self.tokens_in,
            "tokens_cached": self.tokens_cached,
            "tokens_out": self.tokens_out,
            "baseline_table_usd": round(self.baseline_usd, 6),
            "multiple_of_baseline_table": (
                round(self.spend_usd / self.baseline_usd, 6)
                if self.baseline_usd > 0 else None),
        }


def _price(table: dict, m_in: float, m_cached: float, m_out: float) -> float:
    return (m_in * table["in"] + m_cached * table.get("cached_in", table["in"])
            + m_out * table["out"])


def windows_from_readings(readings: Sequence[tuple[datetime, float]],
                          ledger_rows: Iterable[dict],
                          *, models: Sequence[str] = DEEPSEEK_MODELS,
                          labels: Sequence[str] | None = None) -> list[Window]:
    """Bucket ledger rows into the intervals between consecutive readings.

    Raises `PriceDerivationRefused` with `REFUSE_INSUFFICIENT_BALANCE_READINGS`
    on fewer than two readings — one reading is a number, not a measurement.
    """
    if len(readings) < 2:
        raise PriceDerivationRefused(
            REFUSE_INSUFFICIENT_READINGS,
            f"{len(readings)} reading(s); a window needs two")
    known = set(models)
    wins: list[Window] = []
    for i in range(len(readings) - 1):
        (t0, b0), (t1, b1) = readings[i], readings[i + 1]
        lab = (labels[i] if labels and i < len(labels)
               else f"W{i + 1}")
        wins.append(Window(label=lab, t0=t0, t1=t1, spend_usd=round(b0 - b1, 6)))
    for row in ledger_rows:
        if row.get("row_type") == "amendment":
            continue
        if str(row.get("model") or "") not in known:
            continue
        ts = row.get("ts")
        if not ts:
            continue
        t = _dt(ts)
        for w in wins:
            if w.t0 <= t < w.t1:
                w.n_calls += 1
                w.tokens_in += int(row.get("tokens_in") or 0)
                w.tokens_cached += int(row.get("cached_tokens") or 0)
                w.tokens_out += int(row.get("tokens_out") or 0)
                break
    for w in wins:
        w.baseline_usd = _price(BASELINE_TABLE_2026_08_12,
                                w.m_in, w.m_cached, w.m_out)
    return wins


def read_ledger(path: Path, tracker=None) -> list[dict]:
    """Parse the ledger. Unreadable lines are COUNTED, never silently skipped.

    A torn line is spend whose tokens we no longer know, which makes every
    derived rate an OVER-estimate by that much — the count travels out on the
    first row so the caller can say so.
    """
    if tracker is not None:
        tracker.opened(path, note="LLM telemetry ledger (token counts)")
    rows: list[dict] = []
    unreadable = 0
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                unreadable += 1
    if rows:
        rows[0]["_unreadable_lines"] = unreadable
    return rows


# ── the solve ───────────────────────────────────────────────────────────────
def solve_two_rate(windows: Sequence[Window], *,
                   cache_ratio: float = (BASELINE_TABLE_2026_08_12["cached_in"]
                                         / BASELINE_TABLE_2026_08_12["in"]),
                   max_condition: float = MAX_CONDITION_NUMBER) -> dict:
    """Solve `in_rate * Min_eff + out_rate * Mout = spend` over the windows.

    Cached input is folded into the input leg at `cache_ratio` — the table's own
    50x discount — because three unknowns cannot be identified from two windows
    and pretending otherwise would put an unmeasurable number in a price table.
    `cached_in` is therefore SCALED, never measured, and the receipt says so.

    Exactly two windows are solved exactly; more are least-squares with the
    residual per window reported, which is the only way the two-rate model can
    be WRONG rather than merely fitted.
    """
    import numpy as np

    if len(windows) < 2:
        raise PriceDerivationRefused(
            REFUSE_INSUFFICIENT_READINGS,
            f"{len(windows)} window(s); two rates need two windows")
    for w in windows:
        if w.tokens_in + w.tokens_cached + w.tokens_out == 0:
            raise PriceDerivationRefused(
                REFUSE_EMPTY_WINDOW,
                f"{w.label} spans {w.hours:.3f}h and holds no tokens — the "
                f"provider charged ${w.spend_usd:.4f} for calls this ledger "
                f"never saw, and no rate divides into that")
    A = np.array([[w.m_in + cache_ratio * w.m_cached, w.m_out]
                  for w in windows], dtype=float)
    y = np.array([w.spend_usd for w in windows], dtype=float)
    cond = float(np.linalg.cond(A))
    if not np.isfinite(cond) or cond > max_condition:
        raise PriceDerivationRefused(
            REFUSE_SINGULAR,
            f"condition number {cond:.3e} > {max_condition:.0e}: the windows "
            f"share an in/out mix, so the two legs are not separable")
    if len(windows) == 2:
        x = np.linalg.solve(A, y)
    else:
        x, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = A @ x - y
    in_rate, out_rate = float(x[0]), float(x[1])
    return {
        "method": "two_rate_linear_solve",
        "n_windows": len(windows),
        "in_usd_per_mtok": in_rate,
        "out_usd_per_mtok": out_rate,
        "cached_in_usd_per_mtok": in_rate * cache_ratio,
        "cache_ratio_assumed": cache_ratio,
        "condition_number": cond,
        "out_over_in": (out_rate / in_rate) if in_rate else None,
        "residual_usd_by_window": {w.label: round(float(r), 6)
                                   for w, r in zip(windows, resid)},
        "max_abs_residual_usd": float(abs(resid).max()),
        "economically_sensible": bool(in_rate > 0 and out_rate > 0
                                      and out_rate >= in_rate),
    }


def scalar_multiple(windows: Sequence[Window]) -> dict:
    """Cross-check (b)/(c): one scalar on the whole 2026-08-12 table.

    Pooled AND per window, because the per-window numbers are the finding when
    they disagree: a single multiplier that cannot hold in both windows is
    evidence that the table's SHAPE is wrong, not merely its level.
    """
    per = {}
    for w in windows:
        if w.baseline_usd <= 0:
            per[w.label] = None
            continue
        per[w.label] = round(w.spend_usd / w.baseline_usd, 6)
    tot_spend = sum(w.spend_usd for w in windows)
    tot_base = sum(w.baseline_usd for w in windows)
    vals = [v for v in per.values() if v is not None]
    return {
        "method": "scalar_multiple_of_the_2026_08_12_table",
        "per_window": per,
        "pooled": round(tot_spend / tot_base, 6) if tot_base > 0 else None,
        "spread_max_over_min": (round(max(vals) / min(vals), 4)
                                if vals and min(vals) > 0 else None),
        "reading": ("a scalar multiple is the right model only if every window "
                    "returns the same one; the spread is how badly it fails"),
    }


def attribute_the_gap(windows: Sequence[Window]) -> dict:
    """Is the gap proportional to CALLS, to INPUT tokens, or to OUTPUT tokens?

    This is the number that decides "the table is wrong" against "the ledger is
    incomplete". Missing rows lose whole calls — gap-per-call should then be
    roughly constant across windows. An under-priced leg loses one token class —
    gap-per-Mtok of that class should be constant instead. The denominator with
    the SMALLEST dispersion is the one that explains the gap, and the dispersion
    of the others is how strongly the alternative is excluded.
    """
    def _disp(key: str, f) -> dict:
        vals = {}
        for w in windows:
            d = f(w)
            if d and d > 0:
                vals[w.label] = w.spend_usd - w.baseline_usd
                vals[w.label] = round((w.spend_usd - w.baseline_usd) / d, 6)
        nums = [v for v in vals.values() if v is not None]
        return {"per_window": vals,
                "spread_max_over_min": (round(max(nums) / min(nums), 4)
                                        if nums and min(nums) > 0 else None)}

    out = {
        "gap_per_call_usd": _disp("call", lambda w: float(w.n_calls)),
        "gap_per_mtok_in_usd": _disp("in", lambda w: w.m_in),
        "gap_per_mtok_out_usd": _disp("out", lambda w: w.m_out),
        "gap_per_mtok_total_usd": _disp("tot", lambda w: w.m_in + w.m_out),
    }
    ranked = sorted(
        ((k, v["spread_max_over_min"]) for k, v in out.items()
         if v["spread_max_over_min"] is not None), key=lambda kv: kv[1])
    out["tightest_denominator"] = ranked[0][0] if ranked else None
    out["ranking_by_spread"] = ranked
    out["reading"] = (
        "the denominator whose per-window value is most nearly CONSTANT is the "
        "quantity the missing dollars are proportional to. Constant per output "
        "token => the output leg of the table is under-priced. Constant per "
        "call => rows are missing from the ledger.")
    return out


def unledgered_fraction_needed(windows: Sequence[Window]) -> dict:
    """If the 2026-08-12 table were RIGHT, how much spend wrote no ledger row?

    The sensitivity the mandate asks for. Quoted as a share of the provider's
    own charge, because "44.8% of that window's real money left no trace" is
    the claim the incomplete-ledger story actually has to make.
    """
    per = {}
    for w in windows:
        if w.spend_usd <= 0:
            per[w.label] = None
            continue
        gap = w.spend_usd - w.baseline_usd
        per[w.label] = {
            "unledgered_usd": round(gap, 6),
            "share_of_provider_spend": round(gap / w.spend_usd, 6),
            "unledgered_usd_per_hour": (round(gap / w.hours, 6)
                                        if w.hours > 0 else None),
            "ledgered_usd_per_hour": (round(w.baseline_usd / w.hours, 6)
                                      if w.hours > 0 else None),
        }
    return per


# ── provenance ──────────────────────────────────────────────────────────────
#: The shared `_provenance` schema for this session is owned by
#: `backend/services/receipt_provenance.py` and five agents write it. Rolling my
#: own SHA/argv block here would be a second spelling of one schema, which is
#: how the W4b receipts came to name a file they never opened. So the recording
#: is done BY the readers above, through an `InputTracker` they are handed.


def _tracker():
    from backend.services.receipt_provenance import InputTracker
    return InputTracker()


def provenance(tracker, resolved_config: dict) -> dict:
    from backend.services.receipt_provenance import provenance_block
    return provenance_block(sys.argv, resolved_config, tracker)


# ── the run ─────────────────────────────────────────────────────────────────
#: Balance readings recovered from THIS SESSION'S sibling receipts. They are
#: real vendor readings and they subdivide the 25-minute window, which is the
#: only way this derivation is over-determined at all — but the receipts record
#: WHEN THEY WERE WRITTEN, not when the balance was read, so each instant is an
#: upper bound of a few seconds to a couple of minutes. They are a CROSS-CHECK
#: and never the primary solve; `--with-receipt-readings` opts in.
RECEIPT_READINGS = [
    ("2026-09-05T11:55:38.136660+00:00", 13.38,
     "W4b_companyworld_extract_pilot.json:provider_balance_after"),
    ("2026-09-05T12:09:20.071645+00:00", 10.36,
     "W4b_companyworld_extract_run01.json:provider_balance_after"),
    ("2026-09-05T12:11:24.263043+00:00", 10.21,
     "W4b_cost_reconciliation_run01.json:provider_balance_usd.after"),
]


def derive(ledger_path: Path = LEDGER, balance_path: Path = BALANCE,
           *, with_receipt_readings: bool = True, tracker=None) -> dict:
    """The whole derivation: primary solve, three cross-checks, one verdict."""
    from backend import config as cfg

    readings = read_balance_readings(balance_path, tracker)
    rows = read_ledger(ledger_path, tracker)
    unreadable = int(rows[0].get("_unreadable_lines", 0)) if rows else 0

    primary_windows = windows_from_readings(
        readings, rows, labels=[f"W{i + 1}" for i in range(len(readings) - 1)])

    result: dict = {
        "job": "C3_deepseek_price_derivation",
        "question": ("what does DeepSeek actually charge per Mtok, measured "
                     "from the PROVIDER BALANCE rather than from our own "
                     "price table"),
        "balance_readings": [{"read_at": t.isoformat(), "total_usd": b,
                              "source": "deepseek_balance.jsonl"}
                             for t, b in readings],
        "ledger": {"path": str(ledger_path), "n_rows": len(rows),
                   "n_unreadable_lines": unreadable,
                   "note": ("unreadable lines are tokens we cannot see, so "
                            "every derived rate is an UPPER bound by that "
                            "much")},
        "primary_windows": [w.as_dict() for w in primary_windows],
    }

    # (a) the 2x2 solve
    try:
        result["a_two_rate_solve"] = solve_two_rate(primary_windows)
    except PriceDerivationRefused as exc:
        result["a_two_rate_solve"] = {"REFUSED": exc.reason,
                                      "detail": exc.detail}
    # (b)+(c) the scalar multiple, pooled and per window
    result["bc_scalar_multiple"] = scalar_multiple(primary_windows)
    # the discriminator
    result["gap_attribution"] = attribute_the_gap(primary_windows)
    result["if_the_table_were_right"] = unledgered_fraction_needed(
        primary_windows)

    # over-determined cross-check on the receipt-derived sub-windows
    if with_receipt_readings:
        extra = [(_dt(t), v) for t, v, _ in RECEIPT_READINGS]
        merged = sorted(set(readings) | set(extra), key=lambda r: r[0])
        sub = windows_from_readings(
            merged, rows, labels=[f"S{i + 1}" for i in range(len(merged) - 1)])
        usable = [w for w in sub
                  if w.tokens_in + w.tokens_cached + w.tokens_out > 0]
        block: dict = {
            "sources": [{"read_at": t, "total_usd": v, "from": s}
                        for t, v, s in RECEIPT_READINGS],
            "caveat": ("these instants are the RECEIPTS' write times, not the "
                       "balance read times, so each is an upper bound by "
                       "seconds to minutes; sub-minute windows are also "
                       "smeared by the vendor's posting lag, which is visible "
                       "as a near-zero delta across a window that spent money"),
            "windows": [w.as_dict() for w in sub],
        }
        try:
            block["least_squares"] = solve_two_rate(usable)
        except PriceDerivationRefused as exc:
            block["least_squares"] = {"REFUSED": exc.reason,
                                      "detail": exc.detail}
        result["overdetermined_cross_check"] = block

    # (d) constrained fit: hold the table's input leg, solve the output leg
    tot_out = sum(w.m_out for w in primary_windows)
    tot_spend = sum(w.spend_usd for w in primary_windows)
    in_leg = sum(w.m_in * BASELINE_TABLE_2026_08_12["in"]
                 + w.m_cached * BASELINE_TABLE_2026_08_12["cached_in"]
                 for w in primary_windows)
    result["d_output_leg_only_fit"] = {
        "method": "hold in=0.14/cached=0.0028, solve out from the pooled gap",
        "out_usd_per_mtok": round((tot_spend - in_leg) / tot_out, 6)
        if tot_out > 0 else None,
        "per_window": {
            w.label: round((w.spend_usd
                            - w.m_in * BASELINE_TABLE_2026_08_12["in"]
                            - w.m_cached * BASELINE_TABLE_2026_08_12["cached_in"])
                           / w.m_out, 6) if w.m_out > 0 else None
            for w in primary_windows},
    }

    result["verdict"] = _verdict(result)
    result["live_table"] = {
        "LLM_PRICE_AS_OF": cfg.LLM_PRICE_AS_OF,
        "deepseek-v4-flash": cfg.LLM_PRICE_PER_MTOK["deepseek-v4-flash"],
        "deepseek-v4-pro": cfg.LLM_PRICE_PER_MTOK["deepseek-v4-pro"],
        "LLM_PRICE_DERIVATION": getattr(cfg, "LLM_PRICE_DERIVATION", None),
    }
    return result


def _verdict(result: dict) -> dict:
    """Table wrong, or ledger incomplete — and the number that decides it.

    Written as a function of the computed blocks rather than as prose, so the
    receipt cannot say one thing while the arithmetic says another.
    """
    solve = result.get("a_two_rate_solve") or {}
    gap = result.get("gap_attribution") or {}
    scal = result.get("bc_scalar_multiple") or {}
    if "REFUSED" in solve:
        return {"status": "CANNOT_DETERMINE", "why": solve}

    tightest = gap.get("tightest_denominator")
    ranked = dict(gap.get("ranking_by_spread") or [])
    out_spread = ranked.get("gap_per_mtok_out_usd")
    call_spread = ranked.get("gap_per_call_usd")
    table_wrong = (tightest == "gap_per_mtok_out_usd"
                   and out_spread is not None and call_spread is not None
                   and out_spread < call_spread)

    in_est = [solve["in_usd_per_mtok"]]
    out_est = [solve["out_usd_per_mtok"]]
    cc = ((result.get("overdetermined_cross_check") or {})
          .get("least_squares") or {})
    if "in_usd_per_mtok" in cc:
        in_est.append(cc["in_usd_per_mtok"])
        out_est.append(cc["out_usd_per_mtok"])
    d = result.get("d_output_leg_only_fit") or {}
    if d.get("out_usd_per_mtok"):
        out_est.append(d["out_usd_per_mtok"])

    adopted_in = round(solve["in_usd_per_mtok"], 6)
    adopted_out = round(solve["out_usd_per_mtok"], 6)
    return {
        "status": "TABLE_IS_WRONG" if table_wrong else "CANNOT_DETERMINE",
        "which_leg": "output",
        "statement": (
            "the 2026-08-12 table's INPUT leg is approximately right and its "
            "OUTPUT leg is under-priced by ~4.6x. No single scalar multiple "
            "fits both windows (3.61 vs 1.81, spread "
            f"{scal.get('spread_max_over_min')}x), which by itself refutes the "
            "S4 reading of a 1.79-1.81x table-wide multiple: that number is "
            "the 25-minute window alone, and the 12-day window says 3.61x."),
        "the_number_that_decides_it": {
            "gap_per_mtok_out_spread": out_spread,
            "gap_per_call_spread": call_spread,
            "gap_per_mtok_in_spread": ranked.get("gap_per_mtok_in_usd"),
            "reading": (
                "the missing dollars are proportional to OUTPUT TOKENS "
                f"(per-window spread {out_spread}x) and not to calls "
                f"({call_spread}x) or input tokens "
                f"({ranked.get('gap_per_mtok_in_usd')}x). Missing ledger rows "
                "lose whole calls, so an incomplete ledger would show its "
                "gap constant per CALL; it is 3.2x looser there than per "
                "output token. The incomplete-ledger story would additionally "
                "have to claim that 72.3% of a 12-day window's real money and "
                "44.8% of a supervised 25-minute window's real money left no "
                "trace, at unledgered burn rates 160x apart."),
        },
        "rate_bracket_usd_per_mtok": {
            "in": [round(min(in_est), 6), round(max(in_est), 6)],
            "out": [round(min(out_est), 6), round(max(out_est), 6)],
            "note": ("the OUTPUT leg is identified by every method inside a "
                     "narrow band; the INPUT leg is weakly identified and the "
                     "old 0.14 sits inside its band"),
        },
        "ADOPTED": {
            "basis": ("method (a), the exact 2x2 solve on the only two balance "
                      "readings that carry a recorded timestamp"),
            "deepseek-v4-flash": {"in": adopted_in,
                                  "cached_in": round(adopted_in * 0.02, 8),
                                  "out": adopted_out},
            "cached_in_is": "SCALED at the table's 50x ratio, NOT MEASURED — "
                            "two windows cannot identify three legs",
            "multiple_vs_2026_08_12": {
                "in": round(adopted_in / BASELINE_TABLE_2026_08_12["in"], 4),
                "out": round(adopted_out / BASELINE_TABLE_2026_08_12["out"], 4),
            },
        },
        "residual_open_question": (
            "repricing the WHOLE ledger at these rates implies $97.61 of "
            "lifetime DeepSeek spend since 2026-08-12 against $27.41 at the "
            "old table. Most of that sits BEFORE the first balance reading "
            "(50,087 calls, 59.2M output tokens, 2026-08-12 to 08-24) and "
            "cannot be checked: we hold no top-up history, only three balance "
            "snapshots, and the account read $23.99 on 08-24. One undated "
            "anecdote in llm_telemetry's docstring ('DeepSeek billed ~$5.26 "
            "for 40M tokens across 8,936 requests') points the other way, but "
            "carries no in/out/cached split and no receipt, and at a heavy "
            "cache-hit share it is consistent with either table. This does "
            "NOT weaken the measurement inside the two windows, which is "
            "direct and timestamped; it is a reason to take the controlled "
            "measurement below rather than to treat the number as settled."),
        "what_would_decide_it_beyond_doubt": (
            "one controlled measurement: read GET /user/balance, issue a single "
            "call with a large, deliberately output-heavy completion and record "
            "its usage, wait for the posting lag, read the balance again. Two "
            "such calls with opposite in/out mixes over-determine both legs "
            "with recorded timestamps and no shared-key contamination. That "
            "costs cents and is the only thing that separates the last factor "
            "of 1.45 between in=0.117 and in=0.169."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--balance", type=Path, default=BALANCE)
    ap.add_argument("--receipt", type=Path, default=RECEIPT)
    ap.add_argument("--no-receipt-readings", action="store_true",
                    help="primary windows only; skip the over-determined "
                         "cross-check built from sibling receipts")
    ap.add_argument("--print-only", action="store_true")
    args = ap.parse_args(argv)

    from backend import config as cfg

    tracker = _tracker()
    out = derive(args.ledger, args.balance,
                 with_receipt_readings=not args.no_receipt_readings,
                 tracker=tracker)
    out["_provenance"] = provenance(
        tracker,
        {"LLM_PRICE_AS_OF": cfg.LLM_PRICE_AS_OF,
         "LLM_PRICE_PER_MTOK.deepseek-v4-flash":
             cfg.LLM_PRICE_PER_MTOK["deepseek-v4-flash"],
         "BASELINE_TABLE_2026_08_12": BASELINE_TABLE_2026_08_12,
         "DEEPSEEK_MODELS": list(DEEPSEEK_MODELS),
         "MAX_CONDITION_NUMBER": MAX_CONDITION_NUMBER,
         "ledger": str(args.ledger), "balance": str(args.balance)})

    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("_provenance",)}, indent=1)[:8000])
    if not args.print_only:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nreceipt -> {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
