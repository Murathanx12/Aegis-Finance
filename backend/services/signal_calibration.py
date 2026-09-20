"""THE READER for chunk 22's decile maps — a per-name mu_i, or a named refusal.

`scripts/calibrate_signal_return.py` writes one JSON per signal under
`config.CALIB_OUTPUT_DIR`. This module is the only thing allowed to read them,
and it exists so that `roi_rank` asks ONE question — *what does this candidate's
own score decile say its expected return and downside are?* — and gets either
an answer with a receipt path or a sentence saying why there is none.

WHY A FILE AND NOT A CONFIG ROW
===============================
`config.SIGNAL_MEASURED_RETURN` is a hand-copied table: one number per signal
FAMILY, typed off a receipt by a human. Murat's review of 2026-09-20 is about
exactly that shape — *"expected return comes from the leading signal family's
average; downside from the ticker's vol, so among names sharing a family the
rule prefers the lowest-vol name"*. A decile map cannot live in a config: it is
forty numbers per signal per horizon with a CI on each, recomputed whenever the
panel grows. It lives on disk, it carries its own construction block, and the
path it was read from travels onto the decision row as `mu_basis`.

WHAT THIS MODULE REFUSES, AND WHY EACH REFUSAL IS BY NAME
=========================================================
* **No file** for the signal — the ordinary case for a signal nobody has
  calibrated. Named, and the caller falls back to the family row.
* **A SMOKE file.** `..._smoke.json` is a three-year diagnostic the job itself
  refuses to grade. It is skipped by name, never ranked as "newest".
* **A PARTIAL file.** `..._partial.json` is the job's own resume cursor and has
  no family Holm adjustment yet, so it has no verdict. Skipped.
* **A stale file**, dated by its OWN `asof` stamp and never by `st_mtime`
  (session protocol 7: on a fresh checkout every file is "written today").
* **A file with no `verdict`, a wrong `schema`, or no decile row for the
  candidate's decile.** All named.
* **A verdict that is not CALIBRATED.** The read is still returned — WEAK feeds
  EXPLORE's posterior — but `is_exploitable` is False and the caller may not
  size EXPLOIT capital on it. That is the whole of chunk 22's contract with
  chunk 21: EXPLOIT can become non-empty only through measurement.

THE DECILE, AND THE TIE RULE THAT MUST MATCH THE JOB'S
======================================================
`decile_for` uses `np.searchsorted(cuts, score, side="left") + 1`, the SAME
side the job used when it built the table. A reader that broke the tie the
other way would put a live candidate in a neighbouring decile and read someone
else's mu. `test_signal_calibration.py` pins both to the same helper.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backend import config

logger = logging.getLogger(__name__)

SCHEMA = "aegis.signal_calibration.v1"
CALIBRATED = "CALIBRATED"
WEAK = "WEAK"
INVERTED = "INVERTED"
NO_PANEL = "NO_PANEL"
REFUSED = "REFUSED"

#: `<signal>_<YYYY-MM-DD>.json`. The date is cross-checked against the body's
#: own `asof`; a disagreement is a refusal, not a preference for one of them.
_NAME_RE = re.compile(r"^(?P<sig>.+)_(?P<asof>\d{4}-\d{2}-\d{2})\.json$")

#: The 95% normal factor the decile CI is turned back into a standard error
#: with, for EXPLORE's posterior. Named once.
_CI95_Z = 1.959963985


class CalibrationError(ValueError):
    """A calibration file that cannot be trusted as measured."""


def _repo_root() -> Path:
    import os

    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


def calibration_dir(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else _repo_root()
    return base / config.CALIB_OUTPUT_DIR


def _as_date(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


@dataclass
class CalibratedRead:
    """One candidate's own decile, and what the map says about it."""

    signal: str
    verdict: str
    receipt: str
    asof: str
    decile: Optional[int] = None
    horizon_sessions: int = 0
    horizon_months: float = 0.0
    score: Optional[float] = None
    mu_pct: Optional[float] = None
    mu_gross_pct: Optional[float] = None
    mu_is_net: bool = False
    downside_p20_pct: Optional[float] = None
    sd_pct: Optional[float] = None
    ci_lo_pct: Optional[float] = None
    ci_hi_pct: Optional[float] = None
    se_pct: Optional[float] = None
    n_names: Optional[int] = None
    n_date_blocks: Optional[int] = None
    spread_t: Optional[float] = None
    spread_net_pct: Optional[float] = None
    holm_p: Optional[float] = None
    basis: str = ""
    refusals: list = field(default_factory=list)

    @property
    def is_exploitable(self) -> bool:
        """CALIBRATED, with a positive mu for THIS decile. Nothing else.

        This is the single predicate `decision_authority` gates EXPLOIT on, so
        that EXPLOIT can become non-empty only through measurement.

        Deliberately NOT conditioned on the downside: the downside has its own
        declared source and its own declared fallback
        (`config.ROI_DOWNSIDE_SOURCE`, `roi_rank.downside_for`). Coupling them
        would silently send a name whose decile mu is measured back to the
        family average because one percentile of that decile was unusable —
        two different questions answered by one predicate.
        """
        return bool(self.verdict == CALIBRATED and (self.mu_pct or 0.0) > 0.0)

    def usable_downside_pct(self) -> Optional[float]:
        """The MAGNITUDE of the decile's 20th percentile, or None.

        A decile whose 20th percentile is not negative has no measured downside
        at this horizon — one name in five still lost nothing — and returning a
        zero there would divide by zero and hand the name an infinite ROI. None
        sends the caller to the declared vol fallback, which then PRINTS that it
        was used.
        """
        p20 = _f(self.downside_p20_pct)
        if p20 is None or p20 >= 0:
            return None
        return abs(p20)

    def as_row(self) -> dict:
        return {
            "signal": self.signal,
            "calibration_verdict": self.verdict,
            "calibration_receipt": self.receipt,
            "calibration_asof": self.asof,
            "decile": self.decile,
            "horizon_sessions": self.horizon_sessions,
            "horizon_months": self.horizon_months,
            "score": self.score,
            "decile_mean_pct": self.mu_pct,
            "decile_mean_is_net_of_cost": self.mu_is_net,
            "decile_mean_gross_pct": self.mu_gross_pct,
            "decile_p20_pct": self.downside_p20_pct,
            "decile_sd_pct": self.sd_pct,
            "decile_ci_pct": [self.ci_lo_pct, self.ci_hi_pct],
            "decile_se_pct": self.se_pct,
            "decile_n_names": self.n_names,
            "decile_n_date_blocks": self.n_date_blocks,
            "spread_net_pct": self.spread_net_pct,
            "spread_t": self.spread_t,
            "holm_p": self.holm_p,
            "basis": self.basis,
        }


def candidate_files(signal_id: str, *, root: Optional[Path] = None
                    ) -> tuple[list[tuple[date, Path]], list[str]]:
    """(usable (asof, path) pairs newest-first, the files skipped and why)."""
    d = calibration_dir(root)
    skipped: list[str] = []
    out: list[tuple[date, Path]] = []
    if not d.is_dir():
        return out, [f"no calibration directory at {d}"]
    for p in sorted(d.glob(f"{signal_id}_*.json")):
        name = p.name
        if "_smoke" in name:
            skipped.append(f"{name}: a SMOKE file, which the job itself "
                           f"refuses to grade")
            continue
        if ".partial" in name:
            skipped.append(f"{name}: a PARTIAL file — the job's resume cursor, "
                           f"written before the family's Holm adjustment exists")
            continue
        m = _NAME_RE.match(name)
        if not m or m.group("sig") != signal_id:
            skipped.append(f"{name}: not <signal>_<YYYY-MM-DD>.json for "
                           f"{signal_id}")
            continue
        stamp = _as_date(m.group("asof"))
        if stamp is None:
            skipped.append(f"{name}: unparseable date in the filename")
            continue
        out.append((stamp, p))
    out.sort(key=lambda t: (t[0], t[1].name), reverse=True)
    return out, skipped


def latest_for(signal_id: str, *, root: Optional[Path] = None,
               asof: date | str | None = None
               ) -> tuple[Optional[dict], str]:
    """(the newest trustworthy calibration blob for this signal, why or why not).

    Newest by the file's OWN `asof` stamp, cross-checked against the filename.
    Never by `st_mtime`: on a fresh CI checkout every file is written today,
    and a receipt-date gate that fell back to mtime kept finance CI red for two
    days in September (session protocol 7).
    """
    today = _as_date(asof) or date.today()
    pairs, skipped = candidate_files(signal_id, root=root)
    if not pairs:
        return None, (f"no calibration file for {signal_id!r} in "
                      f"{calibration_dir(root)}"
                      + (f" (skipped: {'; '.join(skipped)})" if skipped else ""))
    problems: list[str] = []
    for stamp, p in pairs:
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"{p.name}: unreadable ({type(exc).__name__})")
            continue
        if not isinstance(blob, dict):
            problems.append(f"{p.name}: not a JSON object")
            continue
        if str(blob.get("schema")) != SCHEMA:
            problems.append(f"{p.name}: schema {blob.get('schema')!r}, not "
                            f"{SCHEMA!r}")
            continue
        body_asof = _as_date(blob.get("asof"))
        if body_asof is None or body_asof != stamp:
            problems.append(f"{p.name}: the filename says {stamp} and the body "
                            f"says {blob.get('asof')!r} — a receipt that "
                            f"disagrees with its own name is not a receipt")
            continue
        if not blob.get("verdict"):
            problems.append(f"{p.name}: no verdict")
            continue
        age = (today - stamp).days
        if age > int(config.CALIB_MAX_AGE_DAYS):
            problems.append(
                f"{p.name}: dated {stamp}, which is {age} days before {today} "
                f"and past CALIB_MAX_AGE_DAYS {config.CALIB_MAX_AGE_DAYS}")
            continue
        if age < 0:
            problems.append(f"{p.name}: dated {stamp}, in the FUTURE relative "
                            f"to {today}")
            continue
        blob["_path"] = str(p)
        try:
            blob["_receipt"] = str(p.relative_to(_repo_root()
                                                 if root is None else Path(root)))
        except ValueError:
            blob["_receipt"] = str(p)
        return blob, f"{p.name} (asof {stamp}, {age} day(s) old)"
    return None, (f"every calibration file for {signal_id!r} was refused: "
                  + "; ".join(problems + skipped))


def decile_for(score: Optional[float], cut_points: Any) -> Optional[int]:
    """1..N for a raw score, using the job's OWN tie rule (`side='left'`).

    None when the score is missing or the cut points are absent. Missing is
    missing: a candidate whose leading signal's field never arrived cannot be
    placed in a decile, and placing it in the middle one would be inventing the
    number this whole chunk exists to measure.
    """
    s = _f(score)
    if s is None:
        return None
    try:
        cuts = [float(c) for c in (cut_points or [])]
    except (TypeError, ValueError):
        return None
    if not cuts:
        return None
    import numpy as np

    return int(np.searchsorted(np.asarray(cuts, dtype="float64"), s,
                               side="left")) + 1


def read_for(signal_id: str, score: Optional[float], *,
             horizon_sessions: Optional[int] = None,
             root: Optional[Path] = None,
             asof: date | str | None = None
             ) -> tuple[Optional[CalibratedRead], str]:
    """(this candidate's own decile read, or None, and the reason either way)."""
    blob, why = latest_for(signal_id, root=root, asof=asof)
    if blob is None:
        return None, why
    verdict = str(blob.get("verdict"))
    receipt = str(blob.get("_receipt") or blob.get("_path") or "")
    stamp = str(blob.get("asof"))
    h = int(horizon_sessions if horizon_sessions is not None
            else config.CALIB_DECIDING_HORIZON_SESSIONS)
    base = CalibratedRead(signal=signal_id, verdict=verdict, receipt=receipt,
                          asof=stamp, horizon_sessions=h,
                          horizon_months=h / float(config.CALIB_SESSIONS_PER_MONTH),
                          score=_f(score))
    if verdict in (NO_PANEL, REFUSED):
        base.basis = (f"{signal_id} is {verdict} on {receipt}: "
                      f"{blob.get('verdict_basis')}")
        return base, base.basis
    block = ((blob.get("horizons") or {}).get(str(h)) or {})
    rows = block.get("deciles") or []
    spread = block.get("spread") or {}
    base.spread_t = _f(spread.get("net_t"))
    base.spread_net_pct = _f(spread.get("net_spread_pct"))
    base.holm_p = _f((blob.get("holm") or {}).get("adjusted_p"))
    cuts = blob.get("cut_points")
    d = decile_for(score, cuts)
    base.decile = d
    if not rows:
        base.basis = (f"{receipt} carries no decile table at horizon {h} "
                      f"sessions")
        return base, base.basis
    if d is None:
        base.basis = (
            f"{signal_id} is {verdict} on {receipt}, and this candidate has no "
            f"usable score for it (score={score!r}) or the file carries no cut "
            f"points, so it cannot be placed in a decile. Missing is missing")
        return base, base.basis
    row = next((r for r in rows if int(r.get("decile", -1)) == int(d)), None)
    if row is None:
        base.basis = (
            f"{signal_id} is {verdict} on {receipt}, and its out-of-sample "
            f"table has NO row for decile {d}: the walk-forward panel never "
            f"populated that bucket (ties collapse deciles), so there is no "
            f"measured mu for this candidate")
        return base, base.basis
    base.mu_gross_pct = _f(row.get("mean_abn_pct"))
    net = _f(row.get("mean_abn_net_pct"))
    # The NET cell is what sizes a position. A gross mu would be the family
    # average's defect wearing a decile's clothes: "costs are never omitted".
    base.mu_pct = net if net is not None else base.mu_gross_pct
    base.mu_is_net = net is not None
    base.downside_p20_pct = _f(row.get("p20_abn_pct"))
    base.sd_pct = _f(row.get("sd_abn_pct"))
    base.ci_lo_pct = _f(row.get("ci_lo_pct"))
    base.ci_hi_pct = _f(row.get("ci_hi_pct"))
    if base.ci_lo_pct is not None and base.ci_hi_pct is not None:
        base.se_pct = abs(base.ci_hi_pct - base.ci_lo_pct) / (2.0 * _CI95_Z)
    base.n_names = row.get("n_names")
    base.n_date_blocks = row.get("n_date_blocks")
    net_note = ("NET of this decile's own monthly turnover cost"
                if base.mu_is_net else
                "GROSS — the file carries no net cell for this decile, so the "
                "cost is NOT charged here and the caller must say so")
    base.basis = (
        f"decile {d} of {signal_id} on {receipt} (asof {stamp}, verdict "
        f"{verdict}): mean abnormal {base.mu_pct}% over {h} sessions, 20th "
        f"percentile {base.downside_p20_pct}%, {net_note} "
        f"(gross {base.mu_gross_pct}%), 95% block-bootstrap CI "
        f"[{base.ci_lo_pct}, {base.ci_hi_pct}]%, {base.n_names} name-months "
        f"over {base.n_date_blocks} month blocks; the signal's "
        f"{spread.get('label')} NET spread is {base.spread_net_pct}% at NW t "
        f"{base.spread_t}, Holm-adjusted p {base.holm_p}")
    return base, base.basis


def table(root: Optional[Path] = None, *, asof: date | str | None = None
          ) -> dict:
    """Every leadable signal's current verdict, for a receipt or a status page."""
    out: dict[str, dict] = {}
    try:
        from scripts.calibrate_signal_return import leadable_signals
        lead, excluded = leadable_signals()
    except Exception as exc:  # noqa: BLE001 - the reason IS the result
        return {"verdict": f"CANNOT DETERMINE: {type(exc).__name__}: {exc}"}
    for sid in lead:
        blob, why = latest_for(sid, root=root, asof=asof)
        out[sid] = {
            "verdict": (blob or {}).get("verdict"),
            "receipt": (blob or {}).get("_receipt"),
            "asof": (blob or {}).get("asof"),
            "why": why,
        }
    return {"leadable": out, "excluded_from_the_family": excluded,
            "dir": str(calibration_dir(root))}


__all__ = ["CALIBRATED", "CalibratedRead", "CalibrationError", "INVERTED",
           "NO_PANEL", "REFUSED", "SCHEMA", "WEAK", "calibration_dir",
           "candidate_files", "decile_for", "latest_for", "read_for", "table"]
