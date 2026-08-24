"""Point-in-time option state — the missing input for EVENT_RESPONSE_v1.

WHY THIS EXISTS
===============
`EVENT-RESPONSE-2` is the only adequately-powered result this programme has
produced (IC +0.0315, t 3.19, MDE80 0.0276, survives BH-FDR), and its central
feature is `gap_vs_implied` = |overnight gap| / implied daily move: did the name
move more than the options market had already priced. Ridge gains nothing from
it, so the relationship is non-linear -- which is what "more than priced" should
be.

The screen read that from OptionMetrics `stdopd`, a WRDS research dataset.
`expectation_store._V0_UNKNOWNS` has said `"options_implied_move": "options PIT
store not built"` since G4 v0. This is that store.

THE REASON IT CANNOT WAIT, AND WHY THAT IS UNUSUAL HERE
=======================================================
yfinance option chains are a **snapshot**. There is no history and no backfill:
an implied move that was not captured before the event is gone permanently, and
no amount of later work recovers it. Every day this does not run is a day of
forward evidence destroyed.

That is the opposite of the situation next door. `GRAPH_PROPAGATION_v1` was
built before its live viability was measured, and the mechanism turned out to be
degenerate on the live universe -- building early was wrong there. Here building
early is the only thing that works, because the input is perishable.

MATCHING THE VALIDATED DEFINITION, WHICH IS NOT THE OBVIOUS THING
=================================================================
`stdopd` is a **standardized** surface: OptionMetrics interpolates to a constant
30 and 60 calendar days. yfinance gives whatever expirations happen to exist, so
reading "the nearest expiry" would make the feature drift with the expiry cycle
-- richest just before a monthly, cheapest just after -- and that drift would be
a seasonal pattern the screen never validated, wearing its name.

So this interpolates to CONSTANT 30 and 60 days, linearly in total variance
(sigma^2 * T), which is the standard convention for a vol term structure and the
only one that is arbitrage-sane across maturities. It is NOT bit-identical to
OptionMetrics' method, and that difference is declared rather than hidden:
`method` travels on every row.

WHAT IT DELIBERATELY DOES NOT DO
================================
No skew, no 25-delta, no risk reversal. `stdopd` is ATM-only -- measured, after
the previous session asserted otherwise from the dataset's name -- so the screen
never had those and neither does this. Adding them here would be adding features
with no evidence behind them.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "options-pit-1.0.0"

#: Constant maturities, in CALENDAR days, matching `stdopd`'s days IN (30, 60).
TENORS = (30, 60)

#: Strikes within this fraction of spot count as at-the-money. Same 3% the
#: rest of the codebase uses (`options_intelligence._analyze_chain`), so two
#: surfaces in this repo do not mean different things by "ATM".
ATM_BAND = 0.03

#: Trading days per year — the screen's `implied_move_1d = atm_iv_30 *
#: sqrt(1/252)`. Transcribed, not chosen.
TRADING_DAYS = 252.0

#: An expiry further than this from the target tenor cannot anchor an
#: interpolation. Beyond it the "30-day" IV is really a 9-day or 80-day IV
#: under a 30-day label, which is a silently different feature.
MAX_TENOR_GAP_DAYS = 25


def _root() -> Path:
    import os
    env = os.environ.get("OPTIMUS_LEDGER_DIR")
    base = Path(env) if env else Path(__file__).resolve().parents[1] / "data" / "optimus"
    return base / "options_pit"


class OptionStateUnavailable(RuntimeError):
    """The option state could not be built well enough to store.

    Raised rather than storing a partial row, because a row with a plausible
    `atm_iv_30` interpolated from a 9-day and an 80-day expiry is not a worse
    measurement -- it is a different quantity under the validated one's name,
    and it would be indistinguishable later.
    """


@dataclass
class OptionState:
    ticker: str
    as_of: str                     # the DATE the state describes
    captured_at: str               # when WE observed it — never from a payload
    spot: float
    atm_iv_30: Optional[float]
    atm_iv_60: Optional[float]
    iv30_call: Optional[float]
    iv30_put: Optional[float]
    iv_term_slope: Optional[float]
    iv_put_minus_call_30d: Optional[float]
    implied_move_1d: Optional[float]
    parity_basis: str
    method: str
    n_expiries_used: int
    schema_version: str = SCHEMA_VERSION


# ── the surface ─────────────────────────────────────────────────────────────


def _matched_strike_iv(calls, puts, spot: float
                       ) -> tuple[Optional[float], Optional[float]]:
    """Call and put IV at the SAME strike — the nearest listed to spot.

    WHY NOT TWO SEPARATE ATM AVERAGES. Put-call parity is a statement about one
    strike and one expiry. Averaging IVs over a +/-3% band independently for
    each side lets a DIFFERENT set of strikes enter each leg, so the difference
    carries a strike-composition artefact on top of the parity residual — and
    since skew makes put IV rise as strike falls, an asymmetric strike set
    biases the residual directly.

    Measured 2026-08-24 on 60 live names, the band-average residual had median
    -0.0254 against stdopd's +0.0019, with only 23% positive against 55%. A
    residual that disagrees with its research counterpart by 2.7 vol points is
    not the same feature, and the model splits on absolute thresholds.
    """
    if calls is None or puts is None:
        return None, None
    if not hasattr(calls, "empty") or calls.empty or puts.empty:
        return None, None
    c = calls[calls["impliedVolatility"] > 0]
    p_ = puts[puts["impliedVolatility"] > 0]
    if c.empty or p_.empty:
        return None, None

    common = sorted(set(c["strike"]) & set(p_["strike"]))
    if not common:
        return None, None
    k = min(common, key=lambda x: abs(x - spot))
    if abs(k - spot) > spot * (ATM_BAND * 2):
        return None, None

    ivc = float(c.loc[c["strike"] == k, "impliedVolatility"].mean())
    ivp = float(p_.loc[p_["strike"] == k, "impliedVolatility"].mean())
    ok = (lambda v: v if 0.0 < v < 5.0 else None)
    return ok(ivc), ok(ivp)


def _atm_iv(chain, spot: float) -> Optional[float]:
    """Mean IV of strikes within ATM_BAND of spot."""
    if chain is None or not hasattr(chain, "empty") or chain.empty:
        return None
    c = chain[chain["impliedVolatility"] > 0]
    if c.empty:
        return None
    band = c[(c["strike"] - spot).abs() <= spot * ATM_BAND]
    if band.empty:
        # Nearest strike on either side, rather than nothing: a wide-strike
        # name is thin, not unmeasurable. Recorded via n_expiries_used.
        band = c.iloc[[(c["strike"] - spot).abs().idxmin()]]
    v = float(band["impliedVolatility"].mean())
    return v if 0.0 < v < 5.0 else None


def _interp_constant_maturity(points: list[tuple[float, float]],
                              target_days: int) -> Optional[float]:
    """IV at a CONSTANT maturity, linear in total variance.

    `points` is [(days_to_expiry, iv), ...]. Total variance w = iv^2 * T is
    what interpolates sanely across maturities; interpolating IV directly can
    produce a term structure that admits calendar arbitrage.
    """
    pts = sorted((d, v) for d, v in points if d > 0 and v and v > 0)
    if not pts:
        return None
    t = float(target_days)

    below = [p for p in pts if p[0] <= t]
    above = [p for p in pts if p[0] >= t]
    if below and above:
        d0, v0 = below[-1]
        d1, v1 = above[0]
        if d0 == d1:
            return v0
        w0, w1 = v0 * v0 * d0, v1 * v1 * d1
        w = w0 + (w1 - w0) * (t - d0) / (d1 - d0)
        return math.sqrt(w / t) if w > 0 else None

    # Only one side available — use the nearest expiry, but refuse to call a
    # far-away maturity by this tenor's name.
    d, v = (below[-1] if below else above[0])
    if abs(d - t) > MAX_TENOR_GAP_DAYS:
        return None
    return v


def build_state(ticker: str, as_of: Optional[str] = None,
                *, ticker_obj=None) -> OptionState:
    """Today's option state for one name. `ticker_obj` is injected in tests."""
    import pandas as pd

    now = datetime.now(timezone.utc)
    as_of = as_of or str(now.date())

    if ticker_obj is None:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)

    try:
        hist = ticker_obj.history(period="1d")
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else float("nan")
    except Exception as e:                                   # pragma: no cover
        raise OptionStateUnavailable(f"{ticker}: no spot — {e}") from e
    if not spot or not math.isfinite(spot) or spot <= 0:
        raise OptionStateUnavailable(f"{ticker}: spot unavailable")

    try:
        expiries = list(ticker_obj.options or [])
    except Exception as e:                                   # pragma: no cover
        raise OptionStateUnavailable(f"{ticker}: no expiries — {e}") from e
    if not expiries:
        raise OptionStateUnavailable(f"{ticker}: vendor lists no expirations")

    today = pd.Timestamp(as_of).normalize()
    calls: list[tuple[float, float]] = []
    puts: list[tuple[float, float]] = []
    mcalls: list[tuple[float, float]] = []
    mputs: list[tuple[float, float]] = []
    used = 0
    for e in expiries:
        days = (pd.Timestamp(e).normalize() - today).days
        if days <= 0 or days > max(TENORS) + MAX_TENOR_GAP_DAYS + 30:
            continue
        try:
            ch = ticker_obj.option_chain(e)
        except Exception:                                    # pragma: no cover
            continue
        ivc, ivp = _atm_iv(ch.calls, spot), _atm_iv(ch.puts, spot)
        if ivc:
            calls.append((float(days), ivc))
        if ivp:
            puts.append((float(days), ivp))
        if ivc or ivp:
            used += 1
        # Parity residual is measured at a MATCHED strike, separately from the
        # band averages that feed the level.
        mc, mp = _matched_strike_iv(ch.calls, ch.puts, spot)
        if mc:
            mcalls.append((float(days), mc))
        if mp:
            mputs.append((float(days), mp))

    if used < 2:
        raise OptionStateUnavailable(
            f"{ticker}: only {used} usable expiry in range — a constant-"
            f"maturity surface cannot be interpolated from one point, and "
            f"reading a single expiry as '30-day' would be a different "
            f"feature under the validated one's name")

    c30 = _interp_constant_maturity(calls, 30)
    p30 = _interp_constant_maturity(puts, 30)
    mc30 = _interp_constant_maturity(mcalls, 30)
    mp30 = _interp_constant_maturity(mputs, 30)
    c60 = _interp_constant_maturity(calls, 60)
    p60 = _interp_constant_maturity(puts, 60)

    def _mean(*vs):
        got = [v for v in vs if v is not None]
        return sum(got) / len(got) if got else None

    atm30, atm60 = _mean(c30, p30), _mean(c60, p60)
    if atm30 is None:
        raise OptionStateUnavailable(
            f"{ticker}: no 30-day ATM IV within {MAX_TENOR_GAP_DAYS}d of "
            f"target; the event feature cannot be built from this chain")

    return OptionState(
        ticker=ticker, as_of=as_of,
        captured_at=now.isoformat(),
        spot=round(spot, 4),
        atm_iv_30=round(atm30, 6),
        atm_iv_60=round(atm60, 6) if atm60 is not None else None,
        iv30_call=round(c30, 6) if c30 is not None else None,
        iv30_put=round(p30, 6) if p30 is not None else None,
        iv_term_slope=(round(atm30 - atm60, 6)
                       if atm60 is not None else None),
        # Matched strike, per put-call parity. Falls back to the band
        # difference only when no strike is listed on both sides, and says so.
        iv_put_minus_call_30d=(
            round(mp30 - mc30, 6)
            if (mc30 is not None and mp30 is not None)
            else (round(p30 - c30, 6)
                  if (c30 is not None and p30 is not None) else None)),
        parity_basis=("matched_strike"
                      if (mc30 is not None and mp30 is not None)
                      else "band_average_fallback"),
        implied_move_1d=round(atm30 * math.sqrt(1.0 / TRADING_DAYS), 6),
        method=("constant-maturity 30/60d, linear in total variance; ATM = "
                "mean IV within 3% of spot. NOT bit-identical to "
                "OptionMetrics stdopd."),
        n_expiries_used=used,
    )


# ── the store ───────────────────────────────────────────────────────────────


def _path(as_of: str, root: Optional[Path] = None) -> Path:
    r = root or _root()
    return r / f"option_state_{as_of[:7]}.jsonl"


def existing_keys(as_of: str, root: Optional[Path] = None) -> set[str]:
    p = _path(as_of, root)
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("as_of") == as_of:
            out.add(r.get("ticker"))
    return out


def record(state: OptionState, root: Optional[Path] = None) -> bool:
    """Append one state. WRITE-ONCE per (ticker, as_of).

    A second capture on the same date would silently replace an observation
    made at a different moment, and the whole value of this store is that its
    rows were taken BEFORE their events.
    """
    if state.ticker in existing_keys(state.as_of, root):
        return False
    p = _path(state.as_of, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(state), default=str) + "\n")
    return True


def capture(tickers: list[str], as_of: Optional[str] = None,
            root: Optional[Path] = None, *, builder=build_state) -> dict:
    """One pass over the universe. Never raises for a single bad name."""
    as_of = as_of or str(datetime.now(timezone.utc).date())
    if not tickers:
        raise OptionStateUnavailable(
            "capture over an empty universe — a pass that stored nothing and "
            "reported success is the lift-audit defect")

    out = {"as_of": as_of, "requested": len(tickers), "stored": 0,
           "already_present": 0, "unavailable": 0, "reasons": {}}
    for t in tickers:
        try:
            st = builder(t, as_of)
        except OptionStateUnavailable as e:
            out["unavailable"] += 1
            out["reasons"][t] = str(e)[:200]
            continue
        except Exception as e:                               # pragma: no cover
            out["unavailable"] += 1
            out["reasons"][t] = f"{type(e).__name__}: {e}"[:200]
            continue
        if record(st, root):
            out["stored"] += 1
        else:
            out["already_present"] += 1
    out["coverage"] = round(
        (out["stored"] + out["already_present"]) / len(tickers), 4)
    return out


def health(root: Optional[Path] = None) -> dict:
    """Days held, and whether the store is still accruing.

    A store that silently stopped collecting looks identical to one nobody
    queried, right up until an event needs a row that was never taken.
    """
    r = root or _root()
    files = sorted(r.glob("option_state_*.jsonl")) if r.exists() else []
    if not files:
        return {"status": "ABSENT", "reason": "no option-state file yet",
                "days_held": 0, "rows": 0,
                "consumer": "EVENT_RESPONSE_v1 (not yet registered)"}

    dates, rows = set(), 0
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            if d.get("as_of"):
                dates.add(d["as_of"])

    newest = max(dates) if dates else None
    stale = None
    if newest:
        stale = (datetime.now(timezone.utc).date()
                 - datetime.fromisoformat(newest).date()).days

    status = "ok"
    reason = ""
    if stale is not None and stale > 5:
        status = "DEGRADED"
        reason = (f"no option state captured in {stale} days; this input is "
                  f"PERISHABLE — a chain not snapshotted before its event "
                  f"cannot be recovered")
    return {"status": status, "reason": reason, "days_held": len(dates),
            "rows": rows, "newest": newest, "stale_days": stale,
            "schema_version": SCHEMA_VERSION,
            "consumer": "EVENT_RESPONSE_v1 (not yet registered)"}
