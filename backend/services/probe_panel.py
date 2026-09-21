"""THE PROBE PANEL — the reader that turns graded virtual rows into a posterior.

Roadmap §16.2 / §16.3 chunk 23a, from Murat's review of 2026-09-21: *"We should
be skeptical about claims, not skeptical about experiments. High confidence
determines how much capital we risk. It should not determine whether we are
allowed to learn."*

WHAT THIS CLOSES
================
`decision_authority.assign` had two branches that refused a name for having NO
measured read at all — which is the correct CAPITAL decision and the wrong
LEARNING decision, because nothing accrued and so the read could never become
measured. Chunk 23a sends those names to `PROBE`: weight zero, a virtual row
per horizon, graded by the same grader at its own expiry. This module is the
other end of that loop — it reads the graded rows back and says whether a
hypothesis has become MEASURED.

It computes a posterior and it allocates nothing. The only consumer is
`decision_authority`, which may promote a MEASURED panel read into the EXPLORE
path (`posterior_source = "PROBE_PANEL"`); an unmeasured one leaves the name on
PROBE with the shortfall named.

TWO GATES AND NOT ONE (CANON §58)
=================================
A read is measured only when `n >= config.PROBE_MIN_GRADED` **and**
`n_blocks >= config.PROBE_MIN_BLOCKS`, where a block is a distinct as-of MONTH.
Forty rows written in one week are one observation wearing forty hats: the
names share a market, the window and the regime, and averaging them produces a
standard error that is wrong by the square root of their dependence. The month
count is therefore a gate in its own right and its shortfall is reported
separately, so a reader can tell "not enough rows yet" from "plenty of rows,
all from one fortnight" — opposite findings that ask for opposite work.

EXCESS, NOT RAW (§16.5 item 37)
===============================
The panel's headline is the mean EXCESS return over the benchmark the grader
recorded beside each raw return (`decision_ledger.score_due`). A raw return is
mostly the market; a panel built on raw returns would measure beta and call it
a mechanism. Rows whose benchmark could not be priced fall back to the raw
return and are COUNTED as such on the receipt — never dropped, never silently
mixed in without saying so.

THE SE IS A BLOCK BOOTSTRAP OVER MONTHS
=======================================
`config.PROBE_BOOTSTRAP_DRAWS` resamples of the MONTHS (not the rows), with
replacement, seeded from the hypothesis id and the horizon so a panel read
reproduces exactly when the day is rebuilt. Resampling rows would assume the
rows are independent, which is the assumption the month gate exists to refuse.
"""

from __future__ import annotations

import hashlib
import json
import logging
import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import numpy as np

from backend import config

logger = logging.getLogger(__name__)

#: The direction a virtual row carries. Declared here AND in
#: `decision_contract.DIRECTIONS`; the two are pinned equal by a test rather
#: than imported, because this module must be readable without dragging the
#: contract's import graph (and the contract imports the authority, which
#: imports this).
PROBE_DIRECTION = "PROBE"

#: The ledger state a graded row reaches. Same word `decision_ledger` writes.
SCORED = "SCORED"


@dataclass(frozen=True)
class ProbeRead:
    """One hypothesis at one horizon: what the graded virtual rows say.

    `measured` is the only field a caller may act on, and it is False until
    BOTH gates clear. Everything else is printed so the reader can see how far
    off the panel is rather than only that it is not there yet.
    """

    hypothesis_id: str
    horizon_sessions: int
    n: int
    n_blocks: int
    mean_excess_pct: Optional[float]
    se_pct: Optional[float]
    sign_hit_rate: Optional[float]
    first_asof: Optional[str]
    last_asof: Optional[str]
    measured: bool
    shortfalls: tuple = ()
    n_excess: int = 0
    n_raw_fallback: int = 0
    receipt: str = ""
    basis: str = ""
    blocks: tuple = ()

    @property
    def months(self) -> float:
        """The horizon in months, at 21 sessions to the month."""
        return max(float(self.horizon_sessions) / 21.0, 1e-9)

    def as_row(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "horizon_sessions": int(self.horizon_sessions),
            "n": int(self.n),
            "n_blocks": int(self.n_blocks),
            "mean_excess_pct": self.mean_excess_pct,
            "se_pct": self.se_pct,
            "sign_hit_rate": self.sign_hit_rate,
            "first_asof": self.first_asof,
            "last_asof": self.last_asof,
            "measured": bool(self.measured),
            "shortfalls": list(self.shortfalls),
            "n_excess": int(self.n_excess),
            "n_raw_fallback": int(self.n_raw_fallback),
            "receipt": self.receipt,
            "basis": self.basis,
            "blocks": list(self.blocks),
        }


def ledger_rows(path: Path | None = None) -> list[dict]:
    """Every ledger row. A NAMED indirection so a test replaces the read.

    Imported inside the function on purpose: `decision_ledger` imports
    `decision_contract`, which imports `decision_authority`, which imports this
    module. A module-level import here would close that circle at import time.
    """
    from backend.services import decision_ledger as DL
    return DL.read(path)


def ledger_file(path: Path | None = None) -> str:
    from backend.services import decision_ledger as DL
    return str(DL.ledger_path(path))


def scored_probe_rows(path: Path | None = None, *,
                      asof: date | str | None = None) -> list[dict]:
    """Every `SCORED` row the grader wrote for a PROBE decision, oldest first.

    `asof` is a CUTOFF, not a filter for one day: a panel read rebuilt for a
    past morning must not see a row that was graded after it. Without it, a
    receipt regenerated next March would quietly answer a different question
    from the one the contract asked on the day.
    """
    cutoff = str(asof) if asof is not None else None
    out: list[dict] = []
    for r in ledger_rows(path):
        if str(r.get("state")) != SCORED:
            continue
        detail = r.get("detail")
        if not isinstance(detail, dict):
            continue
        if str(detail.get("direction")) != PROBE_DIRECTION:
            continue
        if not detail.get("hypothesis_id"):
            continue
        day = str(r.get("asof") or detail.get("asof") or "")
        if cutoff is not None and day and day > cutoff:
            continue
        out.append({**detail, "asof": day,
                    "decision_id": str(r.get("decision_id"))})
    return out


def _return_of(row: dict) -> tuple[Optional[float], bool]:
    """(the return to average, was_it_excess). Excess when the grader priced
    the benchmark; the raw return otherwise, and the caller COUNTS which."""
    exc = row.get("excess_return")
    try:
        if exc is not None:
            v = float(exc)
            if v == v:                                   # not NaN
                return v, True
    except (TypeError, ValueError):
        pass
    try:
        raw = row.get("realised_return")
        if raw is None:
            return None, False
        v = float(raw)
        return (v, False) if v == v else (None, False)
    except (TypeError, ValueError):
        return None, False


def _month_of(day: str) -> str:
    return str(day)[:7] if day else "CANNOT DETERMINE"


def _seed(hypothesis_id: str, horizon_sessions: int) -> int:
    blob = f"PROBE_PANEL_v1|{hypothesis_id}|{int(horizon_sessions)}"
    return int.from_bytes(hashlib.sha256(blob.encode("utf-8")).digest()[:8],
                          "big")


def _block_bootstrap_se(by_month: dict, *, draws: int, seed: int
                        ) -> Optional[float]:
    """The se of the mean, resampling MONTHS with replacement.

    Returns None when a single month carries every row: a bootstrap over one
    block has no variation to resample and would print 0.0, which reads as
    certainty and means "there is nothing to resample".
    """
    months = sorted(by_month)
    if len(months) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = np.array([float(np.mean(by_month[m])) for m in months])
    weights = np.array([len(by_month[m]) for m in months], dtype=float)
    idx = rng.integers(0, len(months), size=(int(draws), len(months)))
    picked = means[idx]
    picked_w = weights[idx]
    boot = (picked * picked_w).sum(axis=1) / picked_w.sum(axis=1)
    return float(np.std(boot, ddof=1))


def read_for(hypothesis_id: str, horizon_sessions: int, *,
             path: Path | None = None, asof: date | str | None = None,
             rows: list[dict] | None = None) -> Optional[ProbeRead]:
    """The panel's read for ONE hypothesis at ONE horizon, or None.

    `None` means the panel has never graded a row for this hypothesis at this
    horizon — a statement about the LEDGER, not about the mechanism, and the
    caller says so in its own words. Anything else comes back as a `ProbeRead`
    whose `measured` flag is the only licensing field: False carries the
    shortfalls by name so the receipt can print "9 of 30 grades, 3 of 6 months"
    instead of an absence.

    `rows` is a PRE-LOADED `scored_probe_rows(...)` list. `decision_authority`
    passes one so a day with forty PROBE candidates reads the ledger once
    rather than forty times.
    """
    hid = str(hypothesis_id)
    h = int(horizon_sessions)
    pool = rows if rows is not None else scored_probe_rows(path, asof=asof)
    mine = [r for r in pool
            if str(r.get("hypothesis_id")) == hid
            and int(r.get("horizon_sessions") or 0) == h]
    if not mine:
        return None

    values: list[float] = []
    days: list[str] = []
    by_month: dict[str, list[float]] = {}
    n_excess = 0
    n_raw = 0
    for r in mine:
        v, was_excess = _return_of(r)
        if v is None:
            continue
        values.append(v)
        days.append(str(r.get("asof") or ""))
        by_month.setdefault(_month_of(str(r.get("asof") or "")), []).append(v)
        if was_excess:
            n_excess += 1
        else:
            n_raw += 1

    receipt = (f"{ledger_file(path)} — {len(mine)} SCORED PROBE row(s) for "
               f"hypothesis {hid} at {h} sessions, {len(values)} of them with "
               f"a priced return")
    if not values:
        return ProbeRead(
            hypothesis_id=hid, horizon_sessions=h, n=0, n_blocks=0,
            mean_excess_pct=None, se_pct=None, sign_hit_rate=None,
            first_asof=None, last_asof=None, measured=False,
            shortfalls=(f"0 of {int(config.PROBE_MIN_GRADED)} graded rows: the "
                        f"{len(mine)} SCORED row(s) under this hypothesis all "
                        f"carry an unpriceable return",),
            receipt=receipt,
            basis=("CANNOT DETERMINE: no SCORED PROBE row under this "
                   "hypothesis carries a return that could be priced"))

    n = len(values)
    n_blocks = len(by_month)
    mean_pct = 100.0 * float(statistics.fmean(values))
    se = _block_bootstrap_se(by_month, draws=int(config.PROBE_BOOTSTRAP_DRAWS),
                             seed=_seed(hid, h))
    se_pct = None if se is None else 100.0 * se
    hits = sum(1 for v in values if v > 0)
    min_n = int(config.PROBE_MIN_GRADED)
    min_b = int(config.PROBE_MIN_BLOCKS)

    shortfalls: list[str] = []
    if n < min_n:
        shortfalls.append(
            f"{n} of {min_n} graded rows (config.PROBE_MIN_GRADED): "
            f"{min_n - n} more grade(s) are owed before this hypothesis has a "
            f"measured read")
    if n_blocks < min_b:
        shortfalls.append(
            f"{n_blocks} of {min_b} distinct as-of MONTHS "
            f"(config.PROBE_MIN_BLOCKS, CANON §58): rows from one window are "
            f"one observation wearing many hats, so the month count gates the "
            f"read independently of the row count")
    if se_pct is None:
        shortfalls.append(
            "the block bootstrap has no se: every row falls in one month, so "
            "there is nothing to resample and a printed 0.0 would read as "
            "certainty")
    elif se_pct <= 0:
        shortfalls.append(
            "the block bootstrap returns a se of exactly zero: every month "
            "block carries the same mean, so resampling the months cannot "
            "move the average. That is a degenerate panel, not a certain one "
            "— a zero se would make the Thompson draw a point mass and the "
            "uncertainty bonus nothing")
    measured = not shortfalls

    basis = (
        f"{n} graded PROBE row(s) over {n_blocks} month block(s) "
        f"({min(days) if days else '?'} -> {max(days) if days else '?'}) at "
        f"{h} sessions: mean {mean_pct:+.4f}% "
        f"({n_excess} excess-of-{config.DECISION_BENCHMARK_SYMBOL}, "
        f"{n_raw} raw where the benchmark could not be priced), se "
        f"{'CANNOT DETERMINE' if se_pct is None else f'{se_pct:.4f}%'} from a "
        f"{int(config.PROBE_BOOTSTRAP_DRAWS)}-draw block bootstrap over MONTHS "
        f"seeded {_seed(hid, h)}. MEASURED requires n >= {min_n} AND blocks >= "
        f"{min_b}; this read is "
        f"{'MEASURED' if measured else 'NOT measured (' + '; '.join(shortfalls) + ')'}")

    return ProbeRead(
        hypothesis_id=hid, horizon_sessions=h, n=n, n_blocks=n_blocks,
        mean_excess_pct=round(mean_pct, 6),
        se_pct=(None if se_pct is None else round(se_pct, 6)),
        sign_hit_rate=round(hits / n, 6),
        first_asof=(min(days) if days else None),
        last_asof=(max(days) if days else None),
        measured=measured, shortfalls=tuple(shortfalls),
        n_excess=n_excess, n_raw_fallback=n_raw,
        receipt=receipt, basis=basis,
        blocks=tuple(sorted(by_month)))


def best_read(hypothesis_id: str, *, horizons: Any = None,
              path: Path | None = None, asof: date | str | None = None,
              rows: list[dict] | None = None
              ) -> tuple[Optional[ProbeRead], str]:
    """(the first MEASURED read across the declared horizons, why/why not).

    The horizons are walked in `config.PROBE_HORIZONS_SESSIONS` order —
    shortest first — and the FIRST measured one wins, because that is the
    horizon whose panel filled soonest and the ordering is declared in config
    rather than chosen by the result. When none is measured the sentence names
    the closest one and its shortfall, so the receipt says how far the panel is
    from licensing the name rather than that it is not there.
    """
    hs = tuple(horizons if horizons is not None
               else config.PROBE_HORIZONS_SESSIONS)
    pool = rows if rows is not None else scored_probe_rows(path, asof=asof)
    seen: list[ProbeRead] = []
    for h in hs:
        read = read_for(hypothesis_id, int(h), path=path, asof=asof, rows=pool)
        if read is None:
            continue
        seen.append(read)
        if read.measured:
            return read, (f"the PROBE panel is MEASURED at {int(h)} sessions "
                          f"(first of {list(hs)} to clear both gates): "
                          f"{read.basis}")
    if not seen:
        return None, (f"the PROBE panel holds NO graded row for hypothesis "
                      f"{hypothesis_id} at any of {list(hs)} sessions — the "
                      f"panel starts filling at the shortest horizon once the "
                      f"first virtual row expires")
    best = max(seen, key=lambda r: (r.n, r.n_blocks))
    return None, (f"the PROBE panel is NOT yet measured for hypothesis "
                  f"{hypothesis_id}; its fullest horizon is "
                  f"{best.horizon_sessions} sessions with {best.n} graded "
                  f"row(s) over {best.n_blocks} month block(s) — "
                  f"{'; '.join(best.shortfalls)}")


def census(*, path: Path | None = None, out_dir: Path | None = None,
           asof: date | str | None = None) -> dict:
    """PROBE rows open / graded / hypotheses measured — the scoreboard's line.

    Reads two files and writes none: the contract folder (how many virtual rows
    were WRITTEN and are still waiting for their expiry) and the ledger (how
    many were GRADED, and how many hypotheses that adds up to). A panel that
    has written rows and graded none is the expected reading on the day the
    chunk lands, and it says so rather than printing zeros.
    """
    graded = scored_probe_rows(path, asof=asof)
    scored_ids = {str(r.get("decision_id")) for r in graded}
    written = 0
    open_rows = 0
    hyp_written: set[str] = set()
    folder = Path(out_dir) if out_dir is not None else _decisions_dir()
    if folder.is_dir():
        for p in sorted(folder.glob("*.json")):
            try:
                day = date.fromisoformat(p.stem)
            except ValueError:
                continue
            if asof is not None and str(day) > str(asof):
                continue
            try:
                blob = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for r in blob.get("rows") or []:
                if str(r.get("direction")) != PROBE_DIRECTION:
                    continue
                written += 1
                if r.get("hypothesis_id"):
                    hyp_written.add(str(r.get("hypothesis_id")))
                if str(r.get("decision_id")) not in scored_ids:
                    open_rows += 1

    by_hyp: dict[str, set] = {}
    for r in graded:
        by_hyp.setdefault(str(r.get("hypothesis_id")), set()).add(
            int(r.get("horizon_sessions") or 0))
    measured: list[dict] = []
    for hid, horizons in sorted(by_hyp.items()):
        for h in sorted(horizons):
            read = read_for(hid, h, path=path, asof=asof, rows=graded)
            if read is not None and read.measured:
                measured.append(read.as_row())
    return {
        "receipt": "probe_panel.census",
        "roadmap_item": "chunk 23a",
        "asof": (str(asof) if asof is not None else None),
        "rows_written": written,
        "rows_open": open_rows,
        "rows_graded": len(graded),
        "hypotheses_written": len(hyp_written),
        "hypotheses_with_a_grade": len(by_hyp),
        "hypotheses_measured": len(measured),
        "measured": measured,
        "min_graded": int(config.PROBE_MIN_GRADED),
        "min_blocks": int(config.PROBE_MIN_BLOCKS),
        "ledger": ledger_file(path),
        "basis": (
            f"{written} virtual PROBE row(s) written, {open_rows} still open "
            f"(their own expiry has not passed), {len(graded)} graded; "
            f"{len(measured)} hypothesis-horizon read(s) clear both gates "
            f"(n >= {int(config.PROBE_MIN_GRADED)} AND blocks >= "
            f"{int(config.PROBE_MIN_BLOCKS)}). A PROBE row holds no capital: "
            f"it is a virtual position written so a hypothesis with no panel "
            f"can build one forward, one graded row at a time."),
    }


def _decisions_dir() -> Path:
    from backend.services.decision_contract import DECISIONS_DIR
    return DECISIONS_DIR


__all__ = ["PROBE_DIRECTION", "ProbeRead", "best_read", "census",
           "ledger_file", "ledger_rows", "read_for", "scored_probe_rows"]
