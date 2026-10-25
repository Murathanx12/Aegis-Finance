"""Original stage-1 arithmetic over verified private price inputs; no acquisition.

The production funnel and its process-global failure ledger are never invoked or
modified. This is an inactive, explicit-input seam, not a canonical publisher.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math

from backend.services import funnel_price_bridge as B
from backend.services import opportunity_funnel as F


class EligibilityRefused(ValueError):
    def __init__(self, report: dict):
        self.report = deepcopy(report)
        super().__init__("original eligibility refused: " + ";".join(report["errors"]))


@dataclass(frozen=True)
class StagedEligibility:
    payload: bytes

    @property
    def report(self) -> dict:
        return json.loads(self.payload)


def _original_stage1(close, volume, keep: int) -> tuple[list[F.Candidate], list[dict], dict]:
    """Original inline kernel, plus accounting; no new filters or default values."""
    import numpy as np

    if close.empty:
        raise ValueError("empty_history")
    out: list[F.Candidate] = []
    decisions = []
    for t in close.columns:
        decision = {"ticker": str(t), "status": "filtered", "reason": "insufficient_history"}
        decisions.append(decision)
        px = close[t].dropna()
        if len(px) < F.MIN_HISTORY_DAYS:
            continue
        last = float(px.iloc[-1])
        decision["reason"] = "price_outside_original_range_or_nonfinite"
        if not math.isfinite(last) or not (F.MIN_PRICE <= last <= F.MAX_PRICE):
            continue
        vol_series = volume[t].dropna() if t in volume.columns else None
        decision["reason"] = "volume_missing"
        if vol_series is None or vol_series.empty:
            continue
        # Preserve original alignment semantics. Verified public inputs have no
        # missing joint CV sessions; this does not repair failed acquisition.
        dollar = (px * vol_series.reindex(px.index).fillna(0)).tail(60)
        mdv = float(dollar.median()) if len(dollar) else 0.0
        decision["reason"] = "median_dollar_volume_below_original_floor_or_nonfinite"
        if not math.isfinite(mdv) or mdv < F.MIN_MEDIAN_DOLLAR_VOL:
            continue
        decision["reason"] = "retail_ticket_exceeds_original_adv_fraction"
        if F.RETAIL_TICKET_MAX > F.MAX_TICKET_SHARE_OF_ADV * mdv:
            continue

        rets = px.pct_change().dropna()
        ann_vol = float(rets.std() * np.sqrt(252)) if len(rets) > 60 else None
        mom = None
        if len(px) >= 250:
            mom = float(px.iloc[-21] / px.iloc[-250] - 1.0)
        c = F.Candidate(ticker=str(t), price=last, median_dollar_vol=mdv,
                        vol_annual=ann_vol, mom_12_1=mom, stage=1)
        c.why.append(f"liquid: median 60d dollar volume ${mdv/1e6:.1f}m, so a "
                     f"${F.RETAIL_TICKET_MAX:,.0f} ticket is "
                     f"{100*F.RETAIL_TICKET_MAX/mdv:.2f}% of a day")
        out.append(c)
        decision.update(status="eligible_kept", reason="original_stage1_eligible")

    out.sort(key=lambda c: -(c.median_dollar_vol or 0))
    warnings = {}
    if len(out) <= keep:
        return out, decisions, warnings
    n_bands = F.N_SIZE_STRATA
    per = keep // n_bands
    bands: list[list[F.Candidate]] = [
        out[i * len(out) // n_bands:(i + 1) * len(out) // n_bands]
        for i in range(n_bands)
    ]
    kept: list[F.Candidate] = []
    for b in bands:
        kept.extend(b[:per])
    if len(kept) < keep:
        taken = {c.ticker for c in kept}
        kept.extend([c for c in out if c.ticker not in taken][:keep - len(kept)])
    warnings["stage1_truncated"] = (
        f"{len(out)} names passed eligibility; kept {len(kept)} as a "
        f"{n_bands}-band size-stratified sample rather than the {keep} most "
        f"liquid. Every kept name clears the retail liquidity gate. The "
        f"{len(out) - len(kept)} dropped were never scored.")
    selected = {c.ticker for c in kept}
    for decision in decisions:
        if decision["status"] == "eligible_kept" and decision["ticker"] not in selected:
            decision.update(status="eligible_not_scored", reason="original_size_stratified_sampling")
    kept.sort(key=lambda c: -(c.median_dollar_vol or 0))
    return kept, decisions, warnings


def stage_original_eligibility(*, manifest: dict, artifacts: dict[str, bytes],
                               keep: int = F.STAGE1_KEEP) -> StagedEligibility:
    """Reverify the bridge, then export original stage-1 candidates/accounting.

    Only positive integer keep values supported by the original interface are
    accepted. No strategy alternatives, provider default or file I/O is added.
    """
    report = {"artifact_kind": "original_funnel_stage1_eligibility_v1", "errors": [],
              "eligibility_complete": False, "accounting_complete": False,
              "promotion_eligible": False, "full_funnel_complete": False,
              "downstream": {"stage2": "not_evaluated", "stage3": "not_evaluated",
                             "stage4": "not_evaluated"}, "outcomes": [], "candidates": []}
    try:
        verified = B.stage_verified_prices(manifest=manifest, artifacts=artifacts)
    except B.PriceBridgeRefused as exc:
        report.update(universe=exc.report.get("universe"), price_bridge_refusal=exc.report,
                      outcomes=exc.report.get("outcomes", []), errors=["verified_price_inputs_refused"])
        raise EligibilityRefused(report) from None
    prices = verified.report
    names = prices["universe"]["tickers"]
    report.update(universe=prices["universe"],
                  price_stage_sha256=hashlib.sha256(verified.payload).hexdigest(),
                  manifest_sha256=prices["manifest_sha256"],
                  input_artifact_sha256s=prices["input_artifact_sha256s"],
                  outcomes=[{"ticker": s, "status": "unknown", "reason": "eligibility_not_evaluated"}
                            for s in names])
    if type(keep) is not int or keep <= 0:
        report["errors"] = ["keep_requires_positive_integer"]
        raise EligibilityRefused(report)
    try:
        import pandas as pd

        cvs = {s: prices["inputs"][s]["close_volume"] for s in names}
        close = pd.DataFrame({s: pd.Series(cv["Close"], index=pd.to_datetime(cv["dates"]))
                              for s, cv in cvs.items()})
        volume = pd.DataFrame({s: pd.Series(cv["Volume"], index=pd.to_datetime(cv["dates"]))
                               for s, cv in cvs.items()})
        selected, decisions, warnings = _original_stage1(close, volume, keep)
        # Original arithmetic can overflow on extreme finite inputs. Never
        # serialize NaN/Infinity or turn an arithmetic failure into ineligibility.
        if any(value is not None and not math.isfinite(value) for c in selected
               for value in (c.price, c.median_dollar_vol, c.vol_annual, c.mom_12_1)):
            raise ValueError("nonfinite_original_output")
        report.update(outcomes=decisions, warnings=warnings, keep=keep,
                      eligible_count=sum(r["status"].startswith("eligible_") for r in decisions),
                      selected_count=len(selected), candidates=[c.to_dict() for c in selected],
                      accounting_complete=True, eligibility_complete=True)
        return StagedEligibility(json.dumps(report, sort_keys=True, separators=(",", ":"),
                                             allow_nan=False).encode())
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        report.update(errors=["invalid_or_nonfinite_original_eligibility"],
                      candidates=[], eligibility_complete=False, accounting_complete=False)
        raise EligibilityRefused(report) from None
