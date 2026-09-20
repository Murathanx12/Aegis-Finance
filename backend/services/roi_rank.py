"""THE ROI RULE — rank what is MEASURED, refuse to rank what is not.

Murat, 2026-09-20, verbatim: *"we need to fix the decision making engine. it
shouldnt make bad dessicions but it cant be sure so it doesnt make one. from
good decisions and return potetnials it should go with the highest ROI like we
have talked."* The spec is
`docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md`
Part B; this module is that Part and nothing else.

THE RULE
========
Among candidates that already cleared the HARD gates (verdict, licensed
evidence, positive rank score, PIT, capacity, one-share minimum, worst case
computable — all of them in `investment_committee.compose_book`, all of them
unchanged), rank by::

    roi_score = expected_return_net(horizon) / downside(horizon)

take the top K, and size each by FRACTIONAL KELLY. Nothing here can turn a
`REFUSED` into a `BUY`: this module never sees a candidate the gates rejected,
and it never relaxes a cap. It reorders the admissible and it resizes them.

CHUNK 22 (2026-09-21): WHERE `mu_i` COMES FROM NOW
==================================================
Murat's review of 2026-09-20, issue 1: *"expected return comes from the leading
signal FAMILY's average; downside from the ticker's vol. So among names sharing
a family the rule prefers the lowest-vol name. Useful, but a different
problem."* Both halves are answered here, and neither is a new formula — the
rule is unchanged and the INPUTS moved:

* **`expected_return_net`** now prefers the candidate's OWN score decile, read
  by `signal_calibration` off the newest `CALIBRATED` file under
  `config.CALIB_OUTPUT_DIR`. Two names sharing a signal but sitting in
  different deciles no longer inherit the same number. The decile's own
  turnover cost is already charged in that cell.
* **`downside`** now prefers that decile's MEASURED 20th percentile
  (`config.ROI_DOWNSIDE_SOURCE = "decile_p20"`). The volatility path is kept,
  is the fallback whenever the p20 is unusable, and every row PRINTS which of
  the two produced the number (`downside_source`).
* **`t`** is then the signal's own 21-session spread t off that file, not a
  number copied out of a config by hand.

Precedence, in one sentence: a `CALIBRATED` file beats the family row; `WEAK`
does not reach here at all (it feeds EXPLORE's posterior in
`decision_authority`); `INVERTED` and `NO_PANEL` leave the candidate exactly
where chunk 21 put it, on the family row. Every scored row carries `mu_source`
and `mu_basis` — the receipt path the number came off — so a reader never has
to guess which of the two produced it.

THE HONESTY RULE, WHICH IS THE CENTRE OF THE THING
==================================================
A candidate gets an ROI score **only** when BOTH numbers come from a MEASURED
source:

* `expected_return_net` — the measured net forward return of the candidate's
  LEADING licensed signal, read out of `config.SIGNAL_MEASURED_RETURN`, where
  every row carries its own `receipt` path and `measured_on` date and
  `test_roi_rank.py` asserts every one of those paths exists in this checkout.
  **A signal with no receipt has no row, and a name whose leader has no row is
  not ranked.** There is no default, no prior, no "roughly the equity premium".
* `downside` — the name's own annualised volatility, scaled to the horizon.
  A name with no `vol_annual` is not ranked. Missing is missing, never average
  (the same rule `arena.policies.size_ce_kelly` already enforces).

and only when the leading signal's measured `t` clears `config.ROI_MIN_T`.
That floor is the brief's second clause made executable: *it cannot be sure, so
it does not make one.* A name below the floor is not forced into a ranking on a
number nobody measured well enough — it keeps today's verdict/confidence sizing
and the row PRINTS why, as `roi: NOT_CALIBRATED: <field> — <reason>`.

The rule is therefore a STRICT PARTIAL FUNCTION and the domain it is undefined
on is printed rather than guessed. That is the only difference between this and
relabelling today's heuristic "ROI".

WHAT MAY NOT FEED IT
====================
**No LLM probability is an input here, today or later.** The first run of the
forecast grader (`backend/data/optimus/night_factory_2026-09-20/
grade_forecasts_2026-09-20.json`) measured the swarm at mean probability 0.510
against a base rate of 0.340, Brier 0.2625 against climatology 0.2244 — the
forecasts are overconfident and do not beat the base rate. A number that loses
to its own climatology is not an expected return. The spec's §C gym may one day
contribute a `gut_signal` field with its OWN measured reliability weight; it
enters as one weighted input among licensed signals, never as `expected_return`
and never as a veto.

WHY KELLY IS BORROWED AND NOT REWRITTEN
=======================================
`arena.policies.size_ce_kelly` already implements fractional Kelly with a
declared prior, a per-name cap that truncates WITHOUT redistributing, and a
gross cap — and it already refuses a name with no volatility. A second Kelly in
this repo would be a second thing to get wrong. The mapping is exact rather
than approximate:

    size_ce_kelly gives  w = kelly_fraction * ic_prior * z / sigma

feed it `z = roi_score` and `sigma = vol_horizon`, with
`ic_prior = ROI_DOWNSIDE_Z` (the same z the downside was built from). Then

    w = f * Z * (mu / (Z * sigma)) / sigma = f * mu / sigma^2

which is fractional Kelly on the horizon distribution, exactly. The four
personalities are the `f` — `config.ROI_KELLY_FRACTION_BY_PERSONALITY`, the
same four names `agency.py` uses — and nothing else about the rule changes
between them.

THE CAPS DO NOT MOVE
====================
`max_single_name` is `IC_SINGLE_NAME_TILT_CAP` and `max_gross` is
`IC_TOTAL_TILT_BUDGET`, the same two numbers
`decision_contract.largest_admissible_book()` computes the day's worst case
from. `rank()` re-checks both after sizing and REFUSES rather than trimming, so
no personality and no score can raise the worst case above today's. Session
protocol rule 4, enforced in code instead of remembered.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend import config
from backend.services import signal_calibration

logger = logging.getLogger(__name__)

#: The prefix every un-scored row carries. Spelled once: a reader greps for it.
NOT_CALIBRATED = "NOT_CALIBRATED"

#: Every `SIGNAL_MEASURED_RETURN` row must carry all seven. A row missing one
#: is a REFUSAL, not a row with a hole — a measured return with no receipt is
#: the exact shape of a number that entered a config by hand.
#:
#: `t` and `n_blocks` may be the string `CANNOT DETERMINE: ...` and often are:
#: several receipts in this repo state a monthly NET return and a rank IC t,
#: which is a statistic about the ORDER and not about the return. A row whose
#: `t` is a named absence can never clear `ROI_MIN_T` — which is the correct
#: outcome, and `t_basis` is what tells a reader whether the absence is "nobody
#: computed it" or "the number next to it is a different quantity".
REQUIRED_FIELDS: tuple[str, ...] = (
    "monthly_net_pct", "t", "t_basis", "n_blocks", "net_basis", "receipt",
    "measured_on")

#: Tolerance on the two cap re-checks. Kelly weights are floats; a cap breach
#: worth refusing is a real one, not the last bit of a float.
_CAP_EPS = 1e-9


class MeasuredReturnError(ValueError):
    """A `SIGNAL_MEASURED_RETURN` row that cannot be trusted as measured.

    Raised by `measured_return`, CAUGHT by `rank` and turned into a printed
    `NOT_CALIBRATED` reason: a malformed table must never take down the daily
    contract, and it must never quietly become a number either.
    """


class CapBreach(RuntimeError):
    """Kelly sizing produced a weight or a gross above the declared cap.

    Not clamped here on purpose. `size_ce_kelly` already caps both; if this
    fires, the two layers disagree about what the cap IS, and the worst case on
    the day's receipt would be computed from the wrong one.
    """


def _as_float(value: Any) -> Optional[float]:
    """A finite number, or None. `CANNOT DETERMINE: ...` becomes None, which is
    what a named absence has to mean everywhere it is read."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _repo_root() -> Path:
    """The checkout — the same three lines as `decision_contract._repo_root`."""
    import os

    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


# ===========================================================================
# THE TWO NUMBERS
# ===========================================================================


def measured_return(signal_id: str) -> Optional[dict]:
    """The measured net read for one signal, or None when none is on file.

    None is the ordinary case and it is not a failure: most licensed signals
    in this programme carry an ORDERING verdict and no per-name return, which
    is exactly why `expected_payoff` has been the string NOT CALIBRATED since
    the contract was written.
    """
    table = getattr(config, "SIGNAL_MEASURED_RETURN", {}) or {}
    row = table.get(str(signal_id or ""))
    if row is None:
        return None
    missing = [k for k in REQUIRED_FIELDS if row.get(k) is None]
    if missing:
        raise MeasuredReturnError(
            f"config.SIGNAL_MEASURED_RETURN[{signal_id!r}] is missing "
            f"{missing} — every row carries all of {list(REQUIRED_FIELDS)} or "
            f"it is not a measured read, it is a number somebody typed")
    return dict(row)


def expected_return_net(signal_id: str, *, horizon_months: float
                        ) -> tuple[Optional[float], str, Optional[dict]]:
    """(net return at the horizon as a FRACTION, basis, the measured row).

    Scaled LINEARLY from the monthly read, never compounded. Compounding would
    assert that the measured month repeats every month for two years, which no
    receipt in this repo claims; linear is the smaller of the two numbers and
    the one the receipt supports.
    """
    row = measured_return(signal_id)
    if row is None:
        return None, (
            f"{NOT_CALIBRATED}: expected_return_net — no measured net forward "
            f"return is on file for {signal_id!r} (config.SIGNAL_MEASURED_RETURN "
            f"has no row, and a signal with no receipt gets no number)"), None
    monthly = float(row["monthly_net_pct"]) / 100.0
    er = monthly * float(horizon_months)
    basis = (f"{100 * monthly:+.4f}%/month net x {horizon_months:g} months "
             f"(linear, not compounded), measured {row['measured_on']} at "
             f"t {row['t']} over {row['n_blocks']} blocks; receipt "
             f"{row['receipt']}")
    return er, basis, row


def downside(vol_annual: Optional[float], *, horizon_months: float,
             z: Optional[float] = None) -> tuple[Optional[float], str]:
    """(downside magnitude at the horizon as a FRACTION, basis).

    `z x vol_annual x sqrt(horizon/12)`. A one-sigma horizon move, because the
    quantity being divided into is a POINT estimate of return: a ratio of a
    mean to a one-sigma spread is the Sharpe-shaped number the spec asks for,
    and raising z scales every candidate identically and reorders nothing.
    The z is config (`ROI_DOWNSIDE_Z`) so a reader can see the choice instead
    of finding it inside an expression.

    A missing `vol_annual` returns None. Missing is missing.
    """
    zz = float(config.ROI_DOWNSIDE_Z if z is None else z)
    try:
        vol = float(vol_annual)
    except (TypeError, ValueError):
        vol = float("nan")
    if not math.isfinite(vol) or vol <= 0:
        return None, (
            f"{NOT_CALIBRATED}: downside — the candidate carries no usable "
            f"annualised volatility (vol_annual={vol_annual!r}), so no "
            f"distributional downside can be computed at this horizon and the "
            f"name is not ROI-ranked")
    vol_h = vol * math.sqrt(float(horizon_months) / 12.0)
    return zz * vol_h, (
        f"{zz:g} x annualised vol {100 * vol:.1f}% x sqrt({horizon_months:g}/12) "
        f"= {100 * zz * vol_h:.2f}% at the horizon (config.ROI_DOWNSIDE_Z)")


#: What produced the `mu` on a scored row. Two values and no third.
MU_CALIBRATION = "calibration"
MU_FAMILY_MEAN = "family_mean"

#: What produced the `downside` on a scored row. Two values and no third.
DN_DECILE_P20 = "decile_p20"
DN_VOL = "vol"


@dataclass
class ResolvedReturn:
    """The expected return for ONE candidate, and where the number came from."""

    er: float
    horizon_months: float
    t: Optional[float]
    t_text: Any
    basis: str
    receipt: str
    source: str
    measured_on: str
    n_blocks: Any = None
    verdict: Optional[str] = None
    decile: Optional[int] = None
    downside_p20_pct: Optional[float] = None
    se_pct: Optional[float] = None
    monthly_net_pct: Optional[float] = None


def adapter_field(signal_id: str) -> Optional[str]:
    """The candidate FIELD a signal's score is read off, from the adapters.

    Derived from `recommendation._ADAPTERS` rather than listed: the adapter is
    what actually reads the data, and a second list here would stop matching
    the engine the first time one moved.
    """
    from backend.services.recommendation import _ADAPTERS

    for ad in _ADAPTERS:
        if ad.signal_id == signal_id:
            return ad.field_name
    return None


def raw_score_of(candidates: Optional[dict], ticker: str, rec: Any,
                 signal_id: str) -> Optional[float]:
    """The candidate's RAW score for its leading signal, un-z-scored.

    The calibration's cut points are quantiles of the raw score, so the raw
    value is the only thing that can be placed in a decile. A cross-sectional
    z-score of today's 43 candidates is a different quantity from the score the
    panel was cut on, and using it would read someone else's decile.
    """
    field_name = adapter_field(signal_id)
    if not field_name:
        return None
    cand = (candidates or {}).get(ticker) or {}
    v = cand.get(field_name) if isinstance(cand, dict) else None
    if v is None:
        v = getattr(rec, field_name, None)
    return _as_float(v)


def resolve_expected_return(signal_id: str, *, ticker: str, rec: Any,
                            candidates: Optional[dict],
                            horizon_months: float,
                            asof: Any = None,
                            calibration_root: Optional[Path] = None
                            ) -> tuple[Optional[ResolvedReturn], str, Optional[dict]]:
    """(the resolved read, the reason when there is none, the calibration row).

    PRECEDENCE, and it is the whole of chunk 22's contract with chunk 21:

    1. a **CALIBRATED** file for this signal, at the candidate's OWN decile;
    2. otherwise `config.SIGNAL_MEASURED_RETURN`'s family row, exactly as
       chunk 18c left it.

    `WEAK`, `INVERTED`, `NO_PANEL` and "no file" all fall to (2) and the
    calibration row travels back so the caller can PRINT which verdict was
    seen. A WEAK read is not discarded — `decision_authority` uses it for
    EXPLORE's posterior — it simply may not size EXPLOIT capital.
    """
    cal_row: Optional[dict] = None
    cal_note = "config.ROI_USE_CALIBRATION is off"
    if getattr(config, "ROI_USE_CALIBRATION", False):
        score = raw_score_of(candidates, ticker, rec, signal_id)
        read, cal_note = signal_calibration.read_for(
            signal_id, score, root=calibration_root, asof=asof)
        if read is not None:
            cal_row = read.as_row()
            if read.is_exploitable:
                return ResolvedReturn(
                    er=float(read.mu_pct) / 100.0,
                    horizon_months=float(read.horizon_months),
                    t=_as_float(read.spread_t),
                    t_text=read.spread_t,
                    basis=read.basis,
                    receipt=str(read.receipt),
                    source=MU_CALIBRATION,
                    measured_on=str(read.asof),
                    n_blocks=read.n_date_blocks,
                    verdict=read.verdict,
                    decile=read.decile,
                    downside_p20_pct=read.downside_p20_pct,
                    se_pct=read.se_pct,
                    monthly_net_pct=(float(read.mu_pct)
                                     / max(float(read.horizon_months), 1e-9)),
                ), "", cal_row
    try:
        er, er_basis, row = expected_return_net(signal_id,
                                                horizon_months=horizon_months)
    except MeasuredReturnError as exc:
        return None, (
            f"{NOT_CALIBRATED}: expected_return_net — the measured-return "
            f"table REFUSED to answer for {signal_id!r}: {exc} "
            f"(calibration: {cal_note})"), cal_row
    if er is None or row is None:
        return None, f"{er_basis} (calibration: {cal_note})", cal_row
    return ResolvedReturn(
        er=float(er), horizon_months=float(horizon_months),
        t=_as_float(row["t"]), t_text=row["t"], basis=er_basis,
        receipt=str(row["receipt"]), source=MU_FAMILY_MEAN,
        measured_on=str(row["measured_on"]), n_blocks=row["n_blocks"],
        verdict=(cal_row or {}).get("calibration_verdict"),
        monthly_net_pct=_as_float(row["monthly_net_pct"]),
    ), "", cal_row


def downside_for(read: ResolvedReturn, vol_annual: Optional[float], *,
                 z: float) -> tuple[Optional[float], str, str]:
    """(downside magnitude as a FRACTION, basis, which source produced it).

    `config.ROI_DOWNSIDE_SOURCE` declares the preference; the vol path is never
    deleted and is the fallback whenever the measured p20 is unusable. The row
    PRINTS the source either way, because "the decile's measured 20th
    percentile" and "one sigma of this ticker's vol" are different claims and a
    reader must never have to infer which one sized the position.
    """
    want = str(getattr(config, "ROI_DOWNSIDE_SOURCE", DN_VOL))
    if want == DN_DECILE_P20:
        p20 = _as_float(read.downside_p20_pct)
        if p20 is not None and p20 < 0:
            return abs(p20) / 100.0, (
                f"the MEASURED 20th percentile of decile {read.decile}'s own "
                f"abnormal returns at {read.horizon_months:g} months: "
                f"{p20:.4f}% (config.ROI_DOWNSIDE_SOURCE={want!r}; receipt "
                f"{read.receipt})"), DN_DECILE_P20
        why = (f"decile {read.decile} carries no usable 20th percentile "
               f"({read.downside_p20_pct!r} — a non-negative p20 is not a "
               f"downside)" if read.source == MU_CALIBRATION
               else f"this row's mu came from {read.source}, which carries no "
                    f"decile distribution")
        dn, basis = downside(vol_annual, horizon_months=read.horizon_months, z=z)
        if dn is None:
            return None, basis, DN_VOL
        return dn, (f"{basis} — the VOL FALLBACK, used because {why} "
                    f"(config.ROI_DOWNSIDE_SOURCE={want!r})"), DN_VOL
    dn, basis = downside(vol_annual, horizon_months=read.horizon_months, z=z)
    if dn is None:
        return None, basis, DN_VOL
    return dn, f"{basis} (config.ROI_DOWNSIDE_SOURCE={want!r})", DN_VOL


def kelly_fraction_for(personality: Optional[str] = None) -> tuple[float, str]:
    """(fraction of FULL Kelly, basis). The four personalities, and no fifth.

    An unknown personality falls back to the configured default and SAYS so —
    a typo that silently sized at full Kelly would be the worst possible
    failure of this function.
    """
    table = dict(config.ROI_KELLY_FRACTION_BY_PERSONALITY)
    name = str(personality or config.ROI_DEFAULT_PERSONALITY)
    if name in table:
        return float(table[name]), (
            f"{float(table[name]):g}x full Kelly, the declared fraction for the "
            f"{name!r} personality (config.ROI_KELLY_FRACTION_BY_PERSONALITY)")
    fallback = str(config.ROI_DEFAULT_PERSONALITY)
    return float(table[fallback]), (
        f"{float(table[fallback]):g}x full Kelly — {name!r} is not one of the "
        f"declared personalities {sorted(table)}, so the configured default "
        f"{fallback!r} is used and named")


# ===========================================================================
# THE RANKING
# ===========================================================================


@dataclass
class RoiRanking:
    """What the rule decided, and what it refused to decide.

    `admitted` is the ORDER `compose_book` should size in: scored names best
    first, then the un-scored ones in today's order, truncated to K. Ordering
    the measured ahead of the unmeasured is deliberate and is the only place
    this module changes who gets a scarce slot — an ordering rank and an ROI
    score are not comparable quantities, and a name with a measured return at
    t >= ROI_MIN_T is the better-evidenced of the two by construction. It
    cannot admit a name the gates refused: `rank()` only ever sees survivors.
    """

    admitted: list[Any] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    rows: dict[str, dict] = field(default_factory=dict)
    not_calibrated: dict[str, str] = field(default_factory=dict)
    receipt: dict = field(default_factory=dict)

    def is_scored(self, ticker: str) -> bool:
        return str(ticker) in self.weights

    def weight_for(self, ticker: str) -> Optional[float]:
        return self.weights.get(str(ticker))

    def contract_fields(self, ticker: str) -> dict:
        """The block `decision_contract` puts on the row for this name."""
        t = str(ticker)
        if t in self.rows:
            return dict(self.rows[t])
        return {"roi": self.not_calibrated.get(
            t, f"{NOT_CALIBRATED}: this name never entered the ROI ranking")}


def _sig_of(rec: Any) -> Optional[str]:
    lead = rec.leader() if hasattr(rec, "leader") else None
    return getattr(lead, "signal_id", None)


def _vol_of(candidates: dict, ticker: str, rec: Any) -> Optional[float]:
    cand = (candidates or {}).get(ticker) or {}
    v = cand.get("vol_annual")
    if v is None:
        v = getattr(rec, "vol_annual", None)
    return v


def rank(recs: list[Any], *, candidates: Optional[dict] = None,
         horizon_months: Optional[float] = None,
         personality: Optional[str] = None,
         max_names: Optional[int] = None,
         single_name_cap: Optional[float] = None,
         total_budget: Optional[float] = None,
         asof: Any = None,
         calibration_root: Optional[Path] = None) -> RoiRanking:
    """Rank the ALREADY-ADMISSIBLE by ROI, size the measured ones by Kelly.

    `recs` must arrive in today's order (`(rank, -ranking_score)`), because
    that order is what the un-scored names keep. Everything this function can
    refuse, it refuses by NAME into `not_calibrated`.
    """
    from backend.services.arena.policies import size_ce_kelly

    horizon = float(horizon_months if horizon_months is not None
                    else config.IC_WEALTH_HORIZON_MONTHS)
    k = int(max_names if max_names is not None else config.IC_MAX_TILT_NAMES)
    cap = float(single_name_cap if single_name_cap is not None
                else config.IC_SINGLE_NAME_TILT_CAP)
    budget = float(total_budget if total_budget is not None
                   else config.IC_TOTAL_TILT_BUDGET)
    frac, frac_basis = kelly_fraction_for(personality)
    min_t = float(config.ROI_MIN_T)
    zz = float(config.ROI_DOWNSIDE_Z)

    scored: list[dict] = []
    not_calibrated: dict[str, str] = {}
    by_ticker: dict[str, Any] = {}
    calibration: dict[str, dict] = {}

    for rec in recs or []:
        ticker = str(getattr(rec, "ticker", "") or "")
        if not ticker:
            continue
        by_ticker[ticker] = rec
        sig = _sig_of(rec)
        if not sig:
            not_calibrated[ticker] = (
                f"{NOT_CALIBRATED}: expected_return_net — this name has no "
                f"rank-bearing licensed signal, so there is no measured read to "
                f"attach to it")
            continue
        read, why, cal_row = resolve_expected_return(
            sig, ticker=ticker, rec=rec, candidates=candidates,
            horizon_months=horizon, asof=asof,
            calibration_root=calibration_root)
        if read is None:
            not_calibrated[ticker] = why
            continue
        calibration.setdefault(ticker, cal_row or {})
        t_stat = read.t
        if t_stat is None:
            not_calibrated[ticker] = (
                f"{NOT_CALIBRATED}: confidence — {sig}'s {read.source} read "
                f"states a net return and NO t on that return "
                f"({read.t_text}). Without a t there is nothing for ROI_MIN_T "
                f"to clear, so the name is not ranked "
                f"(receipt {read.receipt})")
            continue
        if t_stat < min_t:
            not_calibrated[ticker] = (
                f"{NOT_CALIBRATED}: confidence — {sig}'s {read.source} read "
                f"carries t {t_stat:.2f}, below ROI_MIN_T {min_t:.2f}. The "
                f"engine is not sure enough about this return to rank the name "
                f"on it, so it does not: the name keeps the verdict/confidence "
                f"sizing and this sentence instead of a score "
                f"(receipt {read.receipt})")
            continue
        if read.er <= 0:
            not_calibrated[ticker] = (
                f"{NOT_CALIBRATED}: expected_return_net — {sig}'s "
                f"{read.source} read is {float(read.monthly_net_pct or 0.0):+.4f}"
                f"%/month, which is not positive, so there is no ROI to rank "
                f"(receipt {read.receipt})")
            continue
        vol_annual = _vol_of(candidates or {}, ticker, rec)
        dn, dn_basis, dn_source = downside_for(read, vol_annual, z=zz)
        if dn is None or dn <= 0:
            not_calibrated[ticker] = dn_basis
            continue
        body = {
            "ticker": ticker,
            "signal": sig,
            "expected_return_net_pct": round(100.0 * read.er, 6),
            "expected_return_basis": read.basis,
            "downside_pct": round(100.0 * dn, 6),
            "downside_basis": dn_basis,
            "downside_source": dn_source,
            "roi_score": round(read.er / dn, 6),
            "roi_basis": read.receipt,
            "mu_source": read.source,
            "mu_basis": read.receipt,
            "roi_horizon_months": read.horizon_months,
            "roi_measured_on": read.measured_on,
            "roi_t": t_stat,
            "roi_n_blocks": read.n_blocks,
            # sigma such that `size_ce_kelly`'s Grinold form collapses to
            # w = f * mu / sigma^2 EXACTLY, whichever source the downside came
            # from. On the vol path dn = z * vol_h, so dn/z == vol_h and this
            # is byte-identical to what chunk 18c fed it.
            "_vol_horizon": float(dn) / float(zz),
        }
        if read.source == MU_CALIBRATION:
            body["calibration_verdict"] = read.verdict
            body["calibration_decile"] = read.decile
            body["calibration_se_pct"] = read.se_pct
        elif (cal_row or {}).get("calibration_verdict"):
            body["calibration_verdict_seen"] = cal_row["calibration_verdict"]
        scored.append(body)

    scored.sort(key=lambda d: (-d["roi_score"], d["ticker"]))
    unscored = [t for t in by_ticker if t in not_calibrated]
    order = [d["ticker"] for d in scored] + unscored
    admitted_tickers = order[:k]
    admitted = [by_ticker[t] for t in admitted_tickers]

    take = [d for d in scored if d["ticker"] in set(admitted_tickers)]
    weights: dict[str, float] = {}
    kelly_receipt: dict = {"sizing": "not_run",
                           "why": "no candidate carried a measured ROI score"}
    if take:
        weights, kelly_receipt = size_ce_kelly(
            [{"ticker": d["ticker"], "score": d["roi_score"]} for d in take],
            {"names": {d["ticker"]: {"vol63": d["_vol_horizon"]} for d in take}},
            ic_prior=zz, kelly_fraction=frac, max_single_name=cap,
            max_gross=budget)
        _refuse_cap_breach(weights, cap=cap, budget=budget)

    rows: dict[str, dict] = {}
    for i, d in enumerate(take, start=1):
        body = {kk: vv for kk, vv in d.items() if not kk.startswith("_")}
        body["roi_rank"] = i
        body["kelly_fraction"] = frac
        body["kelly_fraction_basis"] = frac_basis
        body["kelly_weight"] = round(float(weights.get(d["ticker"], 0.0)), 6)
        rows[d["ticker"]] = body

    for d in scored:
        if d["ticker"] not in rows:
            not_calibrated.setdefault(d["ticker"], (
                f"{NOT_CALIBRATED}: ranked out — this name carried an ROI score "
                f"of {d['roi_score']:.4f} and was outranked inside the "
                f"IC_MAX_TILT_NAMES ({k}) cap"))

    receipt = {
        "rule": "expected_return_net / downside, top K, fractional Kelly",
        "spec": ("docs/research_notes/2026-09-20/"
                 "spec_decision_engine_and_scenario_gym.md §B"),
        "horizon_months": horizon,
        "personality": str(personality or config.ROI_DEFAULT_PERSONALITY),
        "kelly_fraction": frac,
        "kelly_fraction_basis": frac_basis,
        "downside_z": zz,
        "min_t": min_t,
        "max_names": k,
        "single_name_cap": cap,
        "total_budget": budget,
        "n_considered": len(by_ticker),
        "n_scored": len(rows),
        "n_not_calibrated": len(not_calibrated),
        "mu_sources": {t: b.get("mu_source") for t, b in rows.items()},
        "n_mu_from_calibration": sum(1 for b in rows.values()
                                     if b.get("mu_source") == MU_CALIBRATION),
        "downside_sources": {t: b.get("downside_source")
                             for t, b in rows.items()},
        "downside_source_declared": str(
            getattr(config, "ROI_DOWNSIDE_SOURCE", DN_VOL)),
        "calibration_seen": calibration,
        "calibration_table": signal_calibration.table(calibration_root,
                                                      asof=asof),
        "mixed_horizons": len({b.get("roi_horizon_months")
                               for b in rows.values()}) > 1,
        "not_calibrated": dict(not_calibrated),
        "rows_by_ticker": rows,
        "kelly": kelly_receipt,
        "chunk_22": (
            "mu_i is the candidate's OWN score decile's mean from the newest "
            "CALIBRATED file under config.CALIB_OUTPUT_DIR (already net of that "
            "decile's turnover cost), and the downside is that decile's "
            "MEASURED 20th percentile. A signal that is WEAK, INVERTED, "
            "NO_PANEL or uncalibrated leaves the candidate on the family row "
            "exactly as chunk 21 left it, and `mu_source` on every scored row "
            "says which of the two produced the number. `mixed_horizons` True "
            "means two scored rows were measured at different horizons and "
            "their roi_scores are NOT like-for-like comparable — it cannot "
            "happen while only one horizon is calibrated, and it is printed so "
            "that it cannot happen silently."),
        "honesty": (
            "A name is ROI-ranked only when BOTH its leading signal's measured "
            "net return (config.SIGNAL_MEASURED_RETURN, every row with a "
            "receipt path on disk) and its own volatility exist, and only when "
            "that signal's measured t clears ROI_MIN_T. Everything else keeps "
            "the verdict/confidence sizing and prints which field was missing. "
            "No LLM probability is an input: the 2026-09-20 grader measured the "
            "swarm's forecasts at Brier 0.2625 against a climatology of 0.2244."),
    }
    return RoiRanking(admitted=admitted, weights=weights, rows=rows,
                      not_calibrated=not_calibrated, receipt=receipt)


def _refuse_cap_breach(weights: dict[str, float], *, cap: float,
                       budget: float) -> None:
    """Session protocol rule 4, as a gate rather than a memory."""
    for t, w in weights.items():
        if float(w) > cap + _CAP_EPS:
            raise CapBreach(
                f"Kelly sized {t} at {float(w):.6f}, above the declared "
                f"IC_SINGLE_NAME_TILT_CAP {cap:.6f}. The day's worst case is "
                f"computed from the cap, so a weight above it would make the "
                f"printed worst case smaller than the real one.")
    gross = sum(float(w) for w in weights.values())
    if gross > budget + _CAP_EPS:
        raise CapBreach(
            f"Kelly sized a gross tilt of {gross:.6f}, above the declared "
            f"IC_TOTAL_TILT_BUDGET {budget:.6f}.")


def table_receipts(root: Optional[Path] = None) -> dict:
    """Every measured row's receipt path, and whether it EXISTS in this checkout.

    The claim `SIGNAL_MEASURED_RETURN` makes is "this number was measured and
    here is where". `test_roi_rank.py` fails on a missing path, because a
    receipt that is not on disk is prose with a filename.
    """
    base = Path(root) if root is not None else _repo_root()
    out: dict[str, dict] = {}
    for sig, row in (getattr(config, "SIGNAL_MEASURED_RETURN", {}) or {}).items():
        rel = str((row or {}).get("receipt") or "")
        out[sig] = {"receipt": rel, "exists": bool(rel) and (base / rel).exists()}
    return out


__all__ = ["CapBreach", "DN_DECILE_P20", "DN_VOL", "MU_CALIBRATION",
           "MU_FAMILY_MEAN", "MeasuredReturnError", "NOT_CALIBRATED",
           "REQUIRED_FIELDS", "ResolvedReturn", "RoiRanking", "adapter_field",
           "downside", "downside_for", "expected_return_net",
           "kelly_fraction_for", "measured_return", "rank", "raw_score_of",
           "resolve_expected_return", "table_receipts"]
