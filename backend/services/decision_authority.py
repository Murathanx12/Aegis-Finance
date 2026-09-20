"""EXPLOIT, EXPLORE, REFUSED — the authority every admissible row carries.

Roadmap `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§15.2 chunk 21, from Murat's review of 2026-09-20
(`docs/research_notes/2026-09-20/feedback_murat_review_2026-09-20_evening.md`
issue 2). His words, and they are the whole specification:

    "The ROI rule scored 0 of 43 while the old heuristic still says BUY four.
    That is internally inconsistent with 'if it can't be sure, don't make the
    bad decision'. ... EXPLOIT (established evidence, meaningful capital,
    strong thresholds) and EXPLORE (a tiny fixed paper-risk budget into
    uncertain but positive-EV hypotheses so they become proven or disproven).
    Do not require t >= 2 before AEGIS is allowed to learn. ... Uncertain must
    mean INVESTIGATE, never freeze."

THE THREE POPULATIONS, AND THERE IS NO FOURTH
=============================================
Every candidate that has already cleared the HARD gates
(`investment_committee.compose_book`: BUY/WATCH verdict, licensed evidence,
positive ranking score — unchanged, and nothing here can reopen one) is
assigned exactly ONE authority:

* ``EXPLOIT`` — the leading signal carries a **CALIBRATED** decile map
  (`signal_calibration`, chunk 22) AND the ROI rule sized the name above zero
  on it: fractional Kelly inside `IC_SINGLE_NAME_TILT_CAP` and
  `IC_TOTAL_TILT_BUDGET`, unchanged. From 2026-09-21 the family-mean row is no
  longer sufficient even when its `t` clears `ROI_MIN_T` — one number per
  signal, the same for every name that signal leads, is the defect chunk 22
  exists to end, and gating here is what makes "EXPLOIT can become non-empty
  only through measurement" structural rather than a sentence. **On 2026-09-21
  this set is empty and printed empty**: the first calibration run graded all
  three leadable signals WEAK.
* ``EXPLORE`` — a MEASURED but unproven read: the signal has a row in
  `SIGNAL_MEASURED_RETURN` with a positive monthly net, and its ``t`` is below
  the floor or is a named absence. Sized out of a fixed paper-risk budget
  (`config.EXPLORE_BUDGET_PCT`, `config.EXPLORE_PER_NAME_PCT`) allocated by
  THOMPSON SAMPLING over each hypothesis's posterior. Chunk 22: when the
  candidate's own decile carries a **WEAK** calibration, that decile's measured
  mean and its block-bootstrap se ARE the posterior — so two names on one
  signal in different deciles no longer draw from one distribution.
* ``REFUSED`` — everything else, with the sentence that names why. **A name
  with NO measured read is REFUSED, not explored**: exploration is for
  measured-but-unproven, never for nothing. `NO_EVIDENCE` was refused at the
  hard gate and never reaches this module at all.

The four heuristic BUYs therefore stop existing as a third kind of thing. With
`config.IC_LEGACY_HEURISTIC_SIZING` False — the default from 2026-09-20 — a
name is EXPLOIT, EXPLORE or REFUSED and the verdict x confidence sizing that
produced a BUY with no measured ROI is retired behind the flag.

WHY THOMPSON AND NOT A THRESHOLD
================================
A threshold on an uncertain number freezes: it spends nothing on the hypothesis
that would have resolved the uncertainty, so the uncertainty never resolves.
Thompson sampling spends in proportion to the probability that the hypothesis
is the best one available, which is exactly the quantity a fixed paper-risk
budget should be allocated on. The posterior is deliberately crude and entirely
derived from the receipt:

    prior  ~ Normal(monthly_net_pct, se)
    se     = |monthly_net_pct| / t                      when t is a number
    se     = EXPLORE_UNKNOWN_T_SE_MULT x |monthly_net_pct|   when t is absent

A ``t`` that is a named absence (`CANNOT DETERMINE: ...`) is the *widest*
posterior, not an error and not a zero: "nobody measured the t" is more
uncertain than "the t is 1.4", and the sampler must be able to say so.

    exploration_score = draw - cost - risk_penalty(vol) + uncertainty_bonus(se)

all four terms in PERCENT PER MONTH, the unit `monthly_net_pct` is already in,
so nothing here silently mixes an annual number with a monthly one. Every
coefficient is `config`.

DETERMINISM, BECAUSE A RECEIPT MUST REPRODUCE
=============================================
The draw is seeded from the AS-OF DATE and the name
(`EXPLORE_SEED_NAMESPACE|asof|ticker|signal`, sha256 -> 64 bits,
`np.random.default_rng`), so re-running the contract for a past day reproduces
the same allocation, and adding a candidate does not move another candidate's
draw. Every seed is PRINTED on the row.

WHAT THIS MODULE MAY NOT DO
===========================
It may not admit a name the gates refused (it only ever sees survivors), may
not raise a cap, and may not size anything on an LLM number. The explore budget
is ADDITIVE to the tilt budget and bounded by `EXPLORE_BUDGET_PCT`, so the
day's worst case rises by at most that — printed beside the existing worst case
rather than described (session protocol rule 4).
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

import numpy as np

from backend import config
from backend.services import roi_rank, signal_calibration

logger = logging.getLogger(__name__)

#: The three authorities. Spelled once; a reader greps for them.
EXPLOIT = "EXPLOIT"
EXPLORE = "EXPLORE"
REFUSED = "REFUSED"
AUTHORITIES: tuple[str, ...] = (EXPLOIT, EXPLORE, REFUSED)

#: The authorities that may hold capital. `payload`'s capital resolution and
#: the contract's "no row carries BUY without an authority" test both read it.
ACTIVE_AUTHORITIES: tuple[str, ...] = (EXPLOIT, EXPLORE)


def _as_float(value: Any) -> Optional[float]:
    """A finite number, or None. `CANNOT DETERMINE: ...` becomes None."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _asof_str(asof: date | str | None) -> str:
    if asof is None:
        return str(datetime.now(timezone.utc).date())
    if isinstance(asof, date):
        return str(asof)
    return str(asof)


def seed_for(asof: date | str | None, ticker: str, signal: str) -> int:
    """The 64-bit seed for one name's draw, derived and reproducible.

    Derived from the as-of DATE rather than the wall clock: a contract rebuilt
    for 2026-09-20 next March must produce the same allocation it produced on
    the day, or the receipt is not a receipt. Derived per NAME as well as per
    day so that adding a candidate cannot move another candidate's draw — a
    single stream would make yesterday's row depend on today's universe.
    """
    blob = (f"{config.EXPLORE_SEED_NAMESPACE}|{_asof_str(asof)}|{ticker}|"
            f"{signal}")
    return int.from_bytes(hashlib.sha256(blob.encode("utf-8")).digest()[:8],
                          "big")


#: What produced an EXPLORE posterior. Two values and no third.
POSTERIOR_DECILE = "calibration_decile"
POSTERIOR_FAMILY = "family_mean"


def posterior(row: dict, cal: Any = None) -> tuple[float, float, str]:
    """(mean %/month, se %/month, basis). The 3-tuple callers already use."""
    return posterior_read(row, cal)[:3]


def posterior_read(row: dict, cal: Any = None
                   ) -> tuple[float, float, str, str]:
    """(mean %/month, se %/month, basis) for one measured row.

    The mean is the receipt's own `monthly_net_pct`. The se is derived from the
    receipt's own t; a named absence widens it instead of failing, because
    "nobody computed the t" is a statement about uncertainty and this is the
    one place in the programme that is allowed to act on uncertainty.

    CHUNK 22: when a WEAK calibration exists for this candidate's own decile,
    it wins — its mean is that decile's measured net abnormal return and its se
    comes from the decile's own block-bootstrap CI, so two names sharing a
    signal but sitting in different deciles no longer draw from one posterior.
    WEAK is exactly the verdict that belongs here: measured, positive, not
    proven. A CALIBRATED read never reaches this function (it is EXPLOIT's),
    and INVERTED / NO_PANEL leave the candidate on the family row, which is
    where chunk 21 put it.
    """
    if cal is not None and getattr(cal, "verdict", None) == signal_calibration.WEAK:
        mu = _as_float(getattr(cal, "mu_pct", None))
        se_pct = _as_float(getattr(cal, "se_pct", None))
        months = max(float(getattr(cal, "horizon_months", 0.0) or 0.0), 1e-9)
        if mu is not None and se_pct is not None and se_pct > 0:
            mean_m = mu / months
            se_m = se_pct / months
            return mean_m, se_m, (
                f"decile {cal.decile} of {cal.signal} on {cal.receipt} (asof "
                f"{cal.asof}, verdict WEAK): mean {mu:+.4f}% over "
                f"{months:g} month(s) = {mean_m:+.4f} %/mo, se from the "
                f"decile's own 95% block-bootstrap CI "
                f"[{cal.ci_lo_pct}, {cal.ci_hi_pct}]% = {se_m:.4f} %/mo. This "
                f"is the candidate's OWN decile, not its signal family's "
                f"average"), POSTERIOR_DECILE
    mean = float(row["monthly_net_pct"])
    t_stat = _as_float(row.get("t"))
    if t_stat is not None and abs(t_stat) > 0:
        se = abs(mean) / abs(t_stat)
        basis = (f"se = |{mean:+.4f}%/mo| / t {t_stat:.2f} = {se:.4f} %/mo, "
                 f"from the receipt's own t ({row.get('t_basis')})")
    else:
        mult = float(config.EXPLORE_UNKNOWN_T_SE_MULT)
        se = mult * abs(mean)
        basis = (f"se = {mult:g} x |{mean:+.4f}%/mo| = {se:.4f} %/mo — the "
                 f"receipt states NO t on the return ({row.get('t')}), and an "
                 f"unmeasured t is the WIDEST posterior here, never a zero "
                 f"(config.EXPLORE_UNKNOWN_T_SE_MULT)")
    if se <= 0 or not math.isfinite(se):
        se = float(config.EXPLORE_UNKNOWN_T_SE_MULT) * max(abs(mean), 1e-6)
        basis += (" ; the derived se was not positive, so the unknown-t width "
                  "is used and named")
    return mean, se, basis, POSTERIOR_FAMILY


def _cost_pct_per_month(horizon_months: float) -> tuple[float, str]:
    """The declared round-trip cost, amortised over the horizon, in %/month.

    Charged even though every `SIGNAL_MEASURED_RETURN` row is ALREADY net at
    its own ruler (each row's `net_basis` names that ruler, and two of the
    three do not state one). The double charge is deliberate and conservative:
    it can only lower an exploration score, never raise one, and "costs are
    never omitted" is one of the four things `EXPLORE DIRTY, PROMOTE CLEAN`
    does not relax.
    """
    bps = float(config.EXPLORE_COST_ROUND_TRIP_BPS)
    horizon = max(float(horizon_months), 1e-9)
    per_month = (bps / 100.0) / horizon
    return per_month, (
        f"{bps:g} bps round trip / {horizon:g} months = {per_month:.4f} %/mo "
        f"(config.EXPLORE_COST_ROUND_TRIP_BPS), charged ON TOP of the "
        f"receipt's own net ruler — deliberately conservative")


def _risk_penalty(vol_annual: float) -> tuple[float, str]:
    """`coef x monthly vol`, in %/month. A wilder name pays more to be tested."""
    coef = float(config.EXPLORE_RISK_PENALTY_COEF)
    vol_monthly_pct = 100.0 * float(vol_annual) / math.sqrt(12.0)
    return coef * vol_monthly_pct, (
        f"{coef:g} x monthly vol {vol_monthly_pct:.2f}% "
        f"(annualised {100 * float(vol_annual):.1f}% / sqrt(12)) "
        f"= {coef * vol_monthly_pct:.4f} %/mo "
        f"(config.EXPLORE_RISK_PENALTY_COEF)")


def _uncertainty_bonus(se: float) -> tuple[float, str]:
    """`coef x se`, in %/month — the value of RESOLVING the hypothesis.

    The term that makes this an explorer rather than a small exploiter: what a
    paper-risk dollar buys here is information, and the wider the posterior the
    more information the dollar buys.
    """
    coef = float(config.EXPLORE_UNCERTAINTY_BONUS_COEF)
    return coef * float(se), (
        f"{coef:g} x se {se:.4f} = {coef * float(se):.4f} %/mo — the value of "
        f"RESOLVING this hypothesis, not of holding it "
        f"(config.EXPLORE_UNCERTAINTY_BONUS_COEF)")


@dataclass
class AuthoritySplit:
    """Who may hold capital today, at what size, and why every refusal refused.

    `admitted` is the order `compose_book` sizes in: EXPLOIT first (best ROI
    score), then EXPLORE (best exploration score). `weights` holds both
    populations; `authority_of` says which is which, and nothing outside this
    module is allowed to infer one from the other.
    """

    admitted: list[Any] = field(default_factory=list)
    authority_of: dict[str, str] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    blocks: dict[str, dict] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)
    roi: Any = None
    receipt: dict = field(default_factory=dict)

    def authority_for(self, ticker: str) -> str:
        return self.authority_of.get(str(ticker), REFUSED)

    def weight_for(self, ticker: str) -> Optional[float]:
        return self.weights.get(str(ticker))

    def is_exploit(self, ticker: str) -> bool:
        return self.authority_for(ticker) == EXPLOIT

    def is_explore(self, ticker: str) -> bool:
        return self.authority_for(ticker) == EXPLORE

    def exploit_tickers(self) -> list[str]:
        return [t for t, a in self.authority_of.items() if a == EXPLOIT]

    def explore_tickers(self) -> list[str]:
        return [t for t, a in self.authority_of.items() if a == EXPLORE]

    def contract_fields(self, ticker: str) -> dict:
        """The authority block `decision_contract` puts on this name's row."""
        t = str(ticker)
        out: dict = {"authority": self.authority_for(t)}
        block = self.blocks.get(t)
        if block:
            out.update(block)
        elif t in self.refused:
            out["authority_basis"] = self.refused[t]
        else:
            out["authority_basis"] = (
                "not considered — this name never reached the authority split, "
                "because the hard eligibility gates run first and the split "
                "only ever sees the candidates they admitted")
        return out


def _sig_of(rec: Any) -> Optional[str]:
    lead = rec.leader() if hasattr(rec, "leader") else None
    return getattr(lead, "signal_id", None)


def _vol_of(candidates: dict, ticker: str, rec: Any) -> Optional[float]:
    cand = (candidates or {}).get(ticker) or {}
    v = cand.get("vol_annual")
    if v is None:
        v = getattr(rec, "vol_annual", None)
    return _as_float(v)


def assign(recs: list[Any], *, candidates: Optional[dict] = None,
           asof: date | str | None = None,
           horizon_months: Optional[float] = None,
           personality: Optional[str] = None,
           max_names: Optional[int] = None,
           single_name_cap: Optional[float] = None,
           total_budget: Optional[float] = None,
           explore_budget: Optional[float] = None,
           explore_per_name: Optional[float] = None,
           calibration_root: Optional[Any] = None) -> AuthoritySplit:
    """Split the already-admissible into EXPLOIT, EXPLORE and REFUSED.

    `recs` arrive in today's order (`(rank, -ranking_score)`); the hard gates
    have already run. Nothing here can admit a name they refused.
    """
    candidates = candidates or {}
    asof_s = _asof_str(asof)
    horizon = float(horizon_months if horizon_months is not None
                    else config.IC_WEALTH_HORIZON_MONTHS)
    budget = float(explore_budget if explore_budget is not None
                   else config.EXPLORE_BUDGET_PCT)
    per_name = float(explore_per_name if explore_per_name is not None
                     else config.EXPLORE_PER_NAME_PCT)
    min_t = float(config.ROI_MIN_T)

    # 1. EXPLOIT — the ROI rule, unchanged. It scores a name only when both
    #    numbers are measured AND the t clears the floor.
    roi = roi_rank.rank(recs, candidates=candidates, horizon_months=horizon,
                        personality=personality, max_names=max_names,
                        single_name_cap=single_name_cap,
                        total_budget=total_budget, asof=asof_s,
                        calibration_root=calibration_root)

    authority_of: dict[str, str] = {}
    weights: dict[str, float] = {}
    blocks: dict[str, dict] = {}
    refused: dict[str, str] = {}
    by_ticker: dict[str, Any] = {}
    exploit_order: list[str] = []

    for rec in recs or []:
        ticker = str(getattr(rec, "ticker", "") or "")
        if ticker:
            by_ticker[ticker] = rec

    for t, body in (roi.rows or {}).items():
        w = _as_float(roi.weight_for(t)) or 0.0
        if w <= 0:
            # Scored, ranked, and sized at zero by Kelly (a non-positive edge
            # or a missing vol inside the sizer). Not capital, so not EXPLOIT.
            refused[t] = (
                f"EXPLOIT was licensed by the measured t but fractional Kelly "
                f"sized it at {w:.6f} of equity, which is not a position "
                f"(roi_score {body.get('roi_score')}, receipt "
                f"{body.get('roi_basis')})")
            authority_of[t] = REFUSED
            continue
        if (bool(getattr(config, "ROI_USE_CALIBRATION", False))
                and body.get("calibration_verdict")
                != signal_calibration.CALIBRATED):
            # CHUNK 22. EXPLOIT capital is licensed by a MEASURED decile map
            # and by nothing else, so that the set can become non-empty only
            # through measurement. A family-mean row that cleared ROI_MIN_T is
            # still a number typed off a receipt by hand, one per signal, the
            # same for every name that signal leads — which is precisely the
            # defect this chunk exists to end.
            refused[t] = (
                f"the ROI rule scored {t} at {body.get('roi_score')} from its "
                f"{body.get('mu_source')} read, and EXPLOIT requires a "
                f"CALIBRATED decile map for the leading signal "
                f"{body.get('signal')!r}. The calibration says "
                f"{body.get('calibration_verdict') or body.get('calibration_verdict_seen') or 'nothing — no file'}"
                f", so this name is not exploited. It is not frozen either: an "
                f"unproven positive read is EXPLORE's, below "
                f"(config.ROI_USE_CALIBRATION)")
            authority_of[t] = REFUSED
            continue
        authority_of[t] = EXPLOIT
        weights[t] = w
        exploit_order.append(t)
        blocks[t] = {
            "authority_basis": (
                f"EXPLOIT: {body.get('signal')} carries a measured net "
                f"{body.get('expected_return_net_pct'):+.4f}% over the "
                f"{horizon:g}-month horizon at t {body.get('roi_t')}, which "
                f"clears ROI_MIN_T {min_t:.2f}. Sized by fractional Kelly at "
                f"{body.get('kelly_fraction')}x on an ROI score of "
                f"{body.get('roi_score')} "
                f"(mu {body.get('expected_return_net_pct'):+.4f}% over "
                f"downside {body.get('downside_pct')}%); receipt "
                f"{body.get('roi_basis')}"),
            "authority_weight": w,
        }

    # 2. EXPLORE candidates — measured, positive, not yet proven.
    explore_rows: list[dict] = []
    for ticker, rec in by_ticker.items():
        if ticker in authority_of:
            continue
        sig = _sig_of(rec)
        if not sig:
            refused[ticker] = (
                "no rank-bearing licensed signal leads this name, so there is "
                "no measured read to explore and no calibrated read to exploit")
            authority_of[ticker] = REFUSED
            continue
        try:
            row = roi_rank.measured_return(sig)
        except roi_rank.MeasuredReturnError as exc:
            refused[ticker] = (
                f"the measured-return table REFUSED to answer for {sig!r}, so "
                f"neither authority can license this name: {exc}")
            authority_of[ticker] = REFUSED
            continue
        if row is None:
            refused[ticker] = (
                f"NO measured read exists for {sig!r} "
                f"(config.SIGNAL_MEASURED_RETURN has no row). EXPLORE is for "
                f"measured-but-unproven hypotheses, never for nothing: a name "
                f"whose leading signal has never been measured is refused, not "
                f"explored")
            authority_of[ticker] = REFUSED
            continue
        t_clears = _as_float(row.get("t"))
        if t_clears is not None and t_clears >= min_t:
            # CALIBRATED, and it did not become an EXPLOIT position: it was
            # outranked inside the exploit cap, or the sizer refused it. A
            # proven read may not eat the paper-risk budget as a consolation —
            # that budget exists to resolve UNPROVEN hypotheses, and spending
            # it on an already-measured one buys no information at all.
            refused[ticker] = (
                f"{sig} is CALIBRATED (measured t {t_clears:.2f} clears "
                f"ROI_MIN_T {min_t:.2f}), so this name belongs to EXPLOIT and "
                f"did not win a place there: "
                f"{(roi.not_calibrated or {}).get(ticker, 'it was not sized')}. "
                f"EXPLORE is for measured-but-UNPROVEN reads and does not fund "
                f"a proven one as a consolation")
            authority_of[ticker] = REFUSED
            continue
        cal = None
        cal_why = "config.ROI_USE_CALIBRATION is off"
        if bool(getattr(config, "ROI_USE_CALIBRATION", False)):
            cal, cal_why = signal_calibration.read_for(
                sig, roi_rank.raw_score_of(candidates, ticker, rec, sig),
                root=calibration_root, asof=asof_s)
        mean_pct, se, se_basis, post_src = posterior_read(row, cal)
        if mean_pct is None or mean_pct <= float(config.EXPLORE_MIN_NET_PCT):
            refused[ticker] = (
                f"{sig}'s measured net read is {mean_pct}"
                f"%/month, which is not above EXPLORE_MIN_NET_PCT "
                f"{float(config.EXPLORE_MIN_NET_PCT):g} — a hypothesis with no "
                f"positive expected value is not worth paper risk "
                f"({se_basis})")
            authority_of[ticker] = REFUSED
            continue
        vol_annual = _vol_of(candidates, ticker, rec)
        if vol_annual is None or vol_annual <= 0:
            refused[ticker] = (
                f"{sig} is a measured, unproven read worth exploring, but this "
                f"name carries no usable annualised volatility "
                f"(vol_annual={vol_annual!r}), so its risk penalty cannot be "
                f"computed. Missing is missing, never average")
            authority_of[ticker] = REFUSED
            continue

        seed = seed_for(asof_s, ticker, sig)
        draw = float(np.random.default_rng(seed).normal(mean_pct, se))
        cost, cost_basis = _cost_pct_per_month(horizon)
        penalty, penalty_basis = _risk_penalty(vol_annual)
        bonus, bonus_basis = _uncertainty_bonus(se)
        score = draw - cost - penalty + bonus
        t_stat = _as_float(row.get("t"))
        explore_rows.append({
            "ticker": ticker,
            "signal": sig,
            "posterior_mean_pct_per_month": round(mean_pct, 6),
            "posterior_se_pct_per_month": round(se, 6),
            "posterior_basis": se_basis,
            "thompson_draw_pct_per_month": round(draw, 6),
            "thompson_seed": seed,
            "thompson_seed_basis": (
                f"sha256('{config.EXPLORE_SEED_NAMESPACE}|{asof_s}|{ticker}|"
                f"{sig}')[:8] -> numpy default_rng; the AS-OF date seeds it, so "
                f"this row reproduces exactly when the day is rebuilt"),
            "cost_pct_per_month": round(cost, 6),
            "cost_basis": cost_basis,
            "risk_penalty_pct_per_month": round(penalty, 6),
            "risk_penalty_basis": penalty_basis,
            "uncertainty_bonus_pct_per_month": round(bonus, 6),
            "uncertainty_bonus_basis": bonus_basis,
            "exploration_score": round(score, 6),
            "exploration_score_formula": (
                "draw - cost - risk_penalty(vol) + uncertainty_bonus(se), all "
                "terms in percent per month"),
            "measured_t": row.get("t"),
            "measured_t_basis": row.get("t_basis"),
            "receipt": (cal.receipt if post_src == POSTERIOR_DECILE
                        else row.get("receipt")),
            "measured_on": (cal.asof if post_src == POSTERIOR_DECILE
                            else row.get("measured_on")),
            "posterior_source": post_src,
            "calibration_verdict": (getattr(cal, "verdict", None)
                                    if cal is not None else None),
            "calibration_decile": (getattr(cal, "decile", None)
                                   if cal is not None else None),
            "calibration_note": cal_why,
        })

    # 3. THE BUDGET. Ranked by exploration score, filled top-down, and the
    #    budget is a hard ceiling: the (n+1)-th name is REFUSED by name with
    #    its score printed, never squeezed in at half size.
    explore_rows.sort(key=lambda d: (-d["exploration_score"], d["ticker"]))
    allocated = 0.0
    explore_order: list[str] = []
    for i, d in enumerate(explore_rows, start=1):
        t = d["ticker"]
        d["explore_rank"] = i
        if per_name <= 0 or allocated + per_name > budget + 1e-12:
            d["authority"] = REFUSED
            d["weight"] = 0.0
            refused[t] = (
                f"EXPLORE was licensed by a measured, unproven read "
                f"({d['signal']} {d['posterior_mean_pct_per_month']:+.4f}%/mo, "
                f"t {d['measured_t']}), and the paper-risk budget is already "
                f"full: {allocated:.4%} of {budget:.2%} allocated at "
                f"{per_name:.4%} per name, and this name ranked #{i} on an "
                f"exploration score of {d['exploration_score']:+.4f}. The "
                f"budget is a ceiling, not a guide")
            authority_of[t] = REFUSED
            continue
        allocated += per_name
        d["authority"] = EXPLORE
        d["weight"] = per_name
        authority_of[t] = EXPLORE
        weights[t] = per_name
        explore_order.append(t)
        blocks[t] = {
            "authority_basis": (
                f"EXPLORE: {d['signal']} is MEASURED at "
                f"{d['posterior_mean_pct_per_month']:+.4f}%/month net with t "
                f"{d['measured_t']} — unproven against ROI_MIN_T "
                f"{min_t:.2f}, and not equivalent to zero. Thompson draw "
                f"{d['thompson_draw_pct_per_month']:+.4f} from "
                f"Normal({d['posterior_mean_pct_per_month']:+.4f}, "
                f"{d['posterior_se_pct_per_month']:.4f}) at seed "
                f"{d['thompson_seed']} gives an exploration score of "
                f"{d['exploration_score']:+.4f} (rank #{i}); funded at "
                f"{per_name:.4%} of equity out of the "
                f"{budget:.2%} paper-risk budget. Receipt {d['receipt']}"),
            "authority_weight": per_name,
            "explore": {k: v for k, v in d.items() if k != "ticker"},
        }

    # Names the ROI rule considered and could not score, that never became an
    # EXPLORE candidate either, keep `roi_rank`'s own sentence as the refusal.
    for t, why in (roi.not_calibrated or {}).items():
        if t not in authority_of:
            authority_of[t] = REFUSED
            refused.setdefault(t, why)
    for t in by_ticker:
        if t not in authority_of:
            authority_of[t] = REFUSED
            refused.setdefault(t, (
                "no authority licensed this name and no gate named a reason — "
                "CANNOT DETERMINE, which is a defect in this module and not a "
                "verdict about the name"))

    admitted = [by_ticker[t] for t in exploit_order + explore_order
                if t in by_ticker]

    receipt = {
        "rule": ("every admissible candidate carries exactly one authority: "
                 "EXPLOIT (calibrated), EXPLORE (measured but unproven, "
                 "Thompson-allocated out of a fixed paper-risk budget) or "
                 "REFUSED"),
        "roadmap_item": "chunk 21",
        "source": ("docs/research_notes/2026-09-20/"
                   "feedback_murat_review_2026-09-20_evening.md issue 2"),
        "asof": asof_s,
        "legacy_heuristic_sizing": bool(config.IC_LEGACY_HEURISTIC_SIZING),
        "use_calibration": bool(getattr(config, "ROI_USE_CALIBRATION", False)),
        "calibration_table": signal_calibration.table(calibration_root,
                                                      asof=asof_s),
        "exploit_gate": (
            "CHUNK 22: a name reaches EXPLOIT only when its leading signal "
            "carries a CALIBRATED decile map AND the ROI rule sized it above "
            "zero. A family-mean row that cleared ROI_MIN_T is no longer "
            "enough: one number per signal, the same for every name it leads, "
            "is the defect chunk 22 exists to end. EXPLOIT can therefore "
            "become non-empty only through measurement."),
        "min_t": min_t,
        "horizon_months": horizon,
        "n_considered": len(by_ticker),
        "n_exploit": len(exploit_order),
        "n_explore": len(explore_order),
        "n_refused": sum(1 for a in authority_of.values() if a == REFUSED),
        "exploit_tickers": list(exploit_order),
        "explore_tickers": list(explore_order),
        "exploit_weight_total": round(
            sum(weights[t] for t in exploit_order), 6),
        "explore_weight_total": round(allocated, 6),
        "explore_budget_pct": budget,
        "explore_per_name_pct": per_name,
        "explore_slots": (int(budget // per_name) if per_name > 0 else 0),
        "explore_rows": explore_rows,
        "refused": dict(refused),
        "seed_namespace": str(config.EXPLORE_SEED_NAMESPACE),
        "worst_case_added_by_explore": explore_worst_case(
            n_names=len(explore_order), per_name=per_name, budget=budget),
        "honesty": (
            "EXPLOIT is empty whenever no signal's measured t clears "
            "ROI_MIN_T, and it is printed empty rather than filled with the "
            "verdict x confidence heuristic the review retired. EXPLORE never "
            "takes a name with NO measured read: uncertain means INVESTIGATE, "
            "unmeasured means REFUSE. No LLM number is an input to either."),
    }
    return AuthoritySplit(admitted=admitted, authority_of=authority_of,
                          weights=weights, blocks=blocks, refused=refused,
                          roi=roi, receipt=receipt)


def explore_worst_case(*, n_names: int, per_name: float,
                       budget: float) -> dict:
    """What the explore book can lose if every explored name goes to zero.

    Session protocol rule 4 in the shape the contract already prints: no stop
    is declared on a long cash position, so the worst case is the whole
    notional. The budget is what bounds it, and the bound is printed beside the
    day's existing worst case rather than left to be inferred from two configs.
    """
    gross = min(float(n_names) * float(per_name), float(budget))
    return {
        "n_names": int(n_names),
        "per_name_pct": float(per_name),
        "budget_pct": float(budget),
        "gross_over_equity": gross,
        "stop_pct": None,
        "worst_case_pct_of_equity": gross,
        "verdict": (
            f"{int(n_names)} explored name(s) x {float(per_name):.4%} = "
            f"{gross:.4%} of equity, held under the {float(budget):.2%} "
            f"EXPLORE_BUDGET_PCT ceiling; no stop is declared, so the whole "
            f"explore notional is the worst case and it ADDS to the tilt "
            f"worst case rather than sharing its budget"),
    }


__all__ = ["ACTIVE_AUTHORITIES", "AUTHORITIES", "AuthoritySplit", "EXPLOIT",
           "EXPLORE", "POSTERIOR_DECILE", "POSTERIOR_FAMILY", "REFUSED",
           "assign", "explore_worst_case", "posterior", "posterior_read",
           "seed_for"]
