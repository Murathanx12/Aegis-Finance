"""M6 — the exposure the risk layer would hold, and what would change it.

GET  /api/risk-layer/evidence  — everything this layer is permitted to claim,
                                 with each claim's effect, MDE and verdict.
POST /api/risk-layer/exposure  — for a book: the weight now, the last twelve
                                 decisions and what each cost or earned, and
                                 the honest claim.

The endpoint returns a POSITION SIZE. It never returns a ticker to buy, and
that is a finding rather than a missing feature: 206 published predictors
measured on our own panel deliver a median of −0.12%/yr net, and nothing
published clears +3%/yr net among names we can actually trade.
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.cache import cache_get, cache_set
from backend.services import risk_layer as rl

router = APIRouter(prefix="/api/risk-layer", tags=["risk-layer"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_PRICE_TTL = 3600
#: Declared preference ladder (`research_gym.utility`). λ is a preference, not
#: a parameter — a caller may choose one, nothing here tunes one.
_LAMBDA_BY_PERSONALITY = {"preservation": 3.0, "balanced": 3.0,
                          "aggressive": 1.0, "extreme_growth": 1.0}


class Holding(BaseModel):
    ticker: str
    weight: float = Field(gt=0)

    @field_validator("ticker")
    @classmethod
    def _valid(cls, v: str) -> str:
        v = v.strip().upper()
        if not _TICKER_RE.match(v):
            raise ValueError(f"invalid ticker {v!r}")
        return v


class ExposureRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=60)
    target_vol: float = Field(0.15, gt=0.01, le=0.60)
    cap: float = Field(1.0, gt=0.0, le=2.0)
    personality: str = "balanced"

    @field_validator("personality")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in _LAMBDA_BY_PERSONALITY:
            raise ValueError(f"unknown personality {v!r}; declared: "
                             f"{sorted(_LAMBDA_BY_PERSONALITY)}")
        return v


def _book_returns(
        holdings: list[Holding]) -> tuple[list[str], list[float], list[str]]:
    """Weighted daily returns of the book, from whatever history is available.

    Tickers that cannot be priced are DROPPED and the survivors renormalised —
    but the caller is told which, because a book silently missing its largest
    position produces a confident exposure for a portfolio nobody owns.
    """
    import pandas as pd

    from backend.services.data_fetcher import fetch_ticker_history

    frames: dict[str, "pd.Series"] = {}
    missing: list[str] = []
    for h in holdings:
        try:
            hist = fetch_ticker_history(h.ticker, period="2y")
            if hist is None or len(hist) < rl.MIN_OBSERVATIONS:
                missing.append(h.ticker)
                continue
            close = hist["Close"] if "Close" in hist else hist.iloc[:, 0]
            frames[h.ticker] = close.pct_change().dropna()
        except Exception as e:                                   # noqa: BLE001
            logger.warning("risk-layer: %s unavailable (%s)", h.ticker, e)
            missing.append(h.ticker)
    if not frames:
        raise rl.RiskLayerRefused(
            "no holding could be priced, so there is no book to size. This is "
            "reported rather than defaulted to full exposure.")
    df = pd.DataFrame(frames).dropna()
    w = {h.ticker: h.weight for h in holdings if h.ticker in df.columns}
    total = sum(w.values())
    series = sum(df[t] * (wt / total) for t, wt in w.items())
    return [str(d)[:10] for d in series.index], [float(x) for x in series], missing


@router.get("/evidence")
async def evidence() -> dict:
    """Everything this layer may claim — including the negatives, by name."""
    return {"evidence": rl.EVIDENCE.as_dict(),
            "break_even_sacrifice_pct_per_year": rl.BREAK_EVEN_SACRIFICE,
            "lookback_days": rl.LOOKBACK_DAYS,
            "note": ("`established` is |effect| >= MDE, decided when the "
                     "measurement ran. A claim absent from this list has no "
                     "code path that could render it.")}


@router.post("/exposure")
async def exposure(req: ExposureRequest) -> dict:
    key = ("risk-layer:exposure:"
           + ";".join(f"{h.ticker}:{round(h.weight, 4)}"
                      for h in sorted(req.holdings, key=lambda x: x.ticker))
           + f"|{req.target_vol}|{req.cap}|{req.personality}")
    cached = cache_get(key, _PRICE_TTL)
    if cached is not None:
        return cached

    try:
        dates, rets, missing = await asyncio.to_thread(_book_returns,
                                                       req.holdings)
        decision = rl.decide_exposure(rets, target_vol=req.target_vol,
                                      cap=req.cap)
        log = rl.decision_log(dates, rets, target_vol=req.target_vol,
                              cap=req.cap, n=12)
    except rl.RiskLayerRefused as e:
        # 422, not 500 and not a plausible 1.0: the request is well formed and
        # the layer is declining to size a book it cannot measure.
        raise HTTPException(status_code=422, detail=str(e)) from e

    out = {
        "decision": decision.as_dict(),
        "decision_log": log,
        "claim": rl.honest_claim(req.target_vol,
                                 lam=_LAMBDA_BY_PERSONALITY[req.personality]),
        "personality": req.personality,
        "unpriced_holdings": missing,
        "what_would_change_it": {
            "raise_to_cap_below_vol": decision.raise_to_cap_below_vol,
            "halve_above_vol": decision.halve_above_vol,
            "current_vol": decision.realised_vol,
            "statement": (
                f"exposure is {decision.weight:.0%}; it reaches the "
                f"{req.cap:.0%} cap if {rl.LOOKBACK_DAYS}-day realised "
                f"volatility falls below "
                f"{decision.raise_to_cap_below_vol:.1%}, and halves if it "
                f"rises above {decision.halve_above_vol:.1%}"),
        },
    }
    cache_set(key, out)
    return out
