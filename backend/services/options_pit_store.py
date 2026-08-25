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
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "options-pit-1.2.0"
#: 1.2.0 (2026-08-24) makes `q_used` the dividend yield over the OPTION'S OWN
#: WINDOW rather than the trailing 12 months (`OPTIONS-DIVIDEND-WINDOW-1`), and
#: keeps the trailing figure beside it as `q_trailing`. 1.1.0 added
#: `iv_put_minus_call_30d_own`, `r_used`, `q_used` and `price_basis`. `OPTIONS-CONVENTION-1` measured that yfinance's
#: `impliedVolatility` column discounts NOTHING -- inverting our own prices at
#: r = 0, q = 0 reproduces it to 0.0009 -- and that this is the whole 0.026
#: train/serve gap on the put-call residual. So the vendor column is kept (a
#: control, and the thing the standing receipts are written against) and OUR
#: inversion is recorded beside it from the first row.
#:
#: Done NOW rather than after the book exists, for the same reason the
#: collector was: the store is empty, `pi_options_pit` first fires Monday
#: 2026-08-24 15:30 ET, and an option chain has no history to go back for. A
#: day collected without our own residual is a day that can never have one.

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
    """Where option state is written.

    MUST resolve through `config.OPTIMUS_LEDGER_DIR`, like every other
    ledger-writing service. This module used to read an `OPTIMUS_LEDGER_DIR`
    ENVIRONMENT VARIABLE that nothing sets, and fell through to a path inside
    the container image — so on Railway (which sets `AEGIS_DATA_DIR=/data` and
    mounts the volume there) **every deploy destroyed the store**. It never
    held more than one day, and `monday_gate_check` is right that a missed day
    of option chains is gone for good.

    Reading the module attribute at call time, not at import, is deliberate:
    the suite overrides storage by monkeypatching `config.OPTIMUS_LEDGER_DIR`,
    and binding it at import would silently ignore that.
    """
    import os

    from backend import config as _config

    env = os.environ.get("OPTIMUS_LEDGER_DIR")
    base = Path(env) if env else Path(_config.OPTIMUS_LEDGER_DIR)
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
    #: OUR inversion of the same matched strike, under a declared convention.
    #: See SCHEMA_VERSION. `None` when no strike carried a usable two-sided
    #: quote -- never silently filled from the vendor column, because the whole
    #: point is that the two are different quantities.
    iv_put_minus_call_30d_own: Optional[float] = None
    r_used: Optional[float] = None
    #: `q` measured over the OPTION'S OWN WINDOW, which is the one the
    #: inversion used. Zero for the ~70% of names with no ex-date inside 30
    #: days -- see `dividend_yield_over_window`.
    q_used: Optional[float] = None
    #: Trailing-12m yield, kept BESIDE it. It is what the first version used
    #: and what the standing receipts were computed under, so dropping it would
    #: make those numbers unreproducible.
    q_trailing: Optional[float] = None
    price_basis: Optional[str] = None
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
    def ok(v):
        return v if 0.0 < v < 5.0 else None

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


def dividend_yield_over_window(ex_dates, amounts, spot: float, days: float,
                               as_of) -> float:
    """Annualised continuous `q` from dividends expected INSIDE [as_of, +days].

    WHY NOT THE TRAILING YIELD, which is what this used first.
    `OPTIONS-DIVIDEND-WINDOW-1`: for a 30-day option the economically correct
    `q` is the dividend expected inside the option's life, and a quarterly
    payer has an ex-date in a given 30-day window only about a third of the
    time -- measured live, 11 of 39 names. For the other two thirds the correct
    `q` is ZERO, so the trailing yield systematically over-states the carry
    deduction and over-subtracts the put-call residual.

    Measured: switching to this took the residual's median from -0.00338 to
    -0.00179, inside the declared transfer bar for the first time from a model
    that is actually right. (The `q = 0` arm also cleared the bar, but it is
    wrong for the 28% of names that DO pay inside the window, and an arm that
    passes by being wrong in a compensating direction is not shippable.)

    FUTURE EX-DATES ARE PROJECTED from the median historical cadence,
    extrapolated from the last observed one. That is an estimate and it uses
    ONLY past ex-dates, so it is not a look-ahead: it is the same information a
    live collector has at decision time, which is the property that matters.
    """
    import pandas as pd

    if not ex_dates or not amounts or spot <= 0 or days <= 0:
        return 0.0
    idx = pd.to_datetime(pd.Index(ex_dates))
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    if len(idx) < 2:
        return 0.0
    gaps = [g.days for g in (idx[1:] - idx[:-1])]
    cadence = float(sorted(gaps)[len(gaps) // 2]) if gaps else 0.0
    if cadence <= 0:
        return 0.0

    start = pd.Timestamp(as_of).normalize()
    if getattr(start, "tz", None) is not None:
        start = start.tz_localize(None)
    horizon = start + pd.Timedelta(days=float(days))
    amt = float(amounts[-1])

    nxt = idx[-1] + pd.Timedelta(days=cadence)
    # Roll past projected dates already behind us: a stale history must not
    # credit a dividend that has already been paid.
    guard = 0
    while nxt < start and guard < 64:
        nxt = nxt + pd.Timedelta(days=cadence)
        guard += 1
    total, guard = 0.0, 0
    while nxt <= horizon and guard < 64:
        total += amt
        nxt = nxt + pd.Timedelta(days=cadence)
        guard += 1
    if total <= 0:
        return 0.0
    return (total / spot) / (float(days) / 365.0)


def risk_free_simple() -> tuple[float, str]:
    """The declared short rate, simple annual. FRED first, constant on refusal.

    Sourced rather than assumed because the put-call residual moves ~0.0070 per
    percentage point of it (`OPTIONS-CONVENTION-1`), which is larger than the
    entire remaining train/serve gap. A rate nobody checked would decide the
    feature.
    """
    try:
        from backend.services.data_fetcher import DataFetcher
        v = (DataFetcher().fetch_fred_data() or {}).get("fed_funds")
        if v is not None:
            val = float(v.iloc[-1]) if hasattr(v, "iloc") else float(v)
            if math.isfinite(val):
                return val / 100.0, f"FRED:fed_funds={val}"
    except Exception as e:                                   # noqa: BLE001
        logger.warning("options PIT: FRED rate unavailable (%s) — using the "
                       "declared fallback %.4f", type(e).__name__, R_FALLBACK)
    return R_FALLBACK, "declared fallback"


#: Used only when FRED refuses, and LOGGED when it is. Round 1 of
#: OPTIONS-CONVENTION-1 fell back to a constant in silence and reported a
#: verdict the constant decided.
R_FALLBACK = 0.0400


def build_state(ticker: str, as_of: Optional[str] = None,
                *, ticker_obj=None, r_simple: Optional[float] = None
                ) -> OptionState:
    """Today's option state for one name. `ticker_obj` is injected in tests."""
    import pandas as pd

    now = datetime.now(timezone.utc)
    as_of = as_of or str(now.date())

    if ticker_obj is None:
        import yfinance as yf
        ticker_obj = yf.Ticker(ticker)

    q_simple = 0.0
    div_dates: list = []
    div_amounts: list = []
    try:
        # 1y with actions rather than 1d: the SAME single request yields the
        # spot AND the dividend history, and `q` is required by our own
        # inversion. Asking twice would double the collector's vendor calls.
        hist = ticker_obj.history(period="1y", auto_adjust=False, actions=True)
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else float("nan")
        if (not hist.empty and "Dividends" in hist.columns and spot
                and math.isfinite(spot) and spot > 0):
            q_simple = float(hist["Dividends"].tail(252).sum()) / spot
            paid = hist["Dividends"]
            paid = paid[paid > 0]
            div_dates = list(paid.index)
            div_amounts = [float(v) for v in paid.values]
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

    if r_simple is None:
        r_simple, _ = risk_free_simple()

    from backend.services.option_implier import (imply_matched_strike,
                                                 to_continuous)
    r_c = to_continuous(r_simple)

    today = pd.Timestamp(as_of).normalize()
    calls: list[tuple[float, float]] = []
    puts: list[tuple[float, float]] = []
    mcalls: list[tuple[float, float]] = []
    mputs: list[tuple[float, float]] = []
    own: list[tuple[float, float]] = []
    bases: list[str] = []
    q_windows: list[float] = []
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
        # ...and the same strike inverted under OUR convention, off the mid,
        # with `q` measured over THIS expiry's own window (see
        # `dividend_yield_over_window`).
        q_w = dividend_yield_over_window(div_dates, div_amounts, spot,
                                         float(days), as_of)
        q_windows.append(q_w)
        pt = imply_matched_strike(ch.calls, ch.puts, spot, float(days),
                                  r_c, to_continuous(q_w))
        if pt is not None and pt.iv_call and pt.iv_put:
            own.append((float(days), pt.iv_put - pt.iv_call))
            bases.append(pt.price_basis)

    if used < 2:
        raise OptionStateUnavailable(
            f"{ticker}: only {used} usable expiry in range — a constant-"
            f"maturity surface cannot be interpolated from one point, and "
            f"reading a single expiry as '30-day' would be a different "
            f"feature under the validated one's name")

    # A RESIDUAL interpolates linearly in time. The total-variance rule below
    # is for IV LEVELS; applying it to a difference would be a third convention
    # nobody declared.
    own30 = None
    if own:
        pts = sorted(own)
        lo = [p for p in pts if p[0] <= 30]
        hi = [p for p in pts if p[0] >= 30]
        if lo and hi:
            d0, v0 = lo[-1]
            d1, v1 = hi[0]
            own30 = v0 if d0 == d1 else v0 + (v1 - v0) * (30 - d0) / (d1 - d0)
        else:
            d, v = (lo[-1] if lo else hi[0])
            own30 = v if abs(d - 30) <= MAX_TENOR_GAP_DAYS else None

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
        iv_put_minus_call_30d_own=(round(own30, 6) if own30 is not None
                                   else None),
        r_used=round(r_simple, 6),
        q_used=round(float(sum(q_windows) / len(q_windows)), 6)
        if q_windows else 0.0,
        q_trailing=round(q_simple, 6),
        price_basis=(max(set(bases), key=bases.count) if bases else None),
        implied_move_1d=round(atm30 * math.sqrt(1.0 / TRADING_DAYS), 6),
        method=("constant-maturity 30/60d, linear in total variance; ATM = "
                "mean IV within 3% of spot. NOT bit-identical to "
                "OptionMetrics stdopd."),
        n_expiries_used=used,
    )


# ── the store ───────────────────────────────────────────────────────────────


def _legacy_root() -> Path:
    """Where this store used to write: inside the container image.

    Kept as a named function, not a comment, because rows here cannot be
    recreated — an option chain has no history — so the path has to stay
    reachable long enough to be migrated off.
    """
    return Path(__file__).resolve().parents[1] / "data" / "optimus" / "options_pit"


def migrate_legacy(root: Optional[Path] = None) -> dict:
    """Move any option state left at the legacy image path onto the volume.

    WRITE-ONCE per (ticker, as_of) via `record`, so re-running is safe and a
    row already on the volume is never replaced by an image copy of itself.
    Returns a receipt rather than logging only — a migration nobody can audit
    is the thing this codebase keeps paying for.
    """
    legacy = _legacy_root()
    dest = root or _root()
    out = {"legacy_root": str(legacy), "dest_root": str(dest),
           "files": 0, "rows_seen": 0, "rows_migrated": 0, "skipped": 0}
    if not legacy.exists() or legacy.resolve() == Path(dest).resolve():
        out["status"] = "nothing to do"
        return out
    for f in sorted(legacy.glob("option_state_*.jsonl")):
        out["files"] += 1
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            out["rows_seen"] += 1
            try:
                state = OptionState(**rec)
            except TypeError:
                out["skipped"] += 1
                continue
            if record(state, dest):
                out["rows_migrated"] += 1
            else:
                out["skipped"] += 1
    out["status"] = "ok"
    if out["rows_migrated"]:
        logger.warning("options_pit: migrated %s row(s) off the legacy image "
                       "path %s onto %s", out["rows_migrated"], legacy, dest)
    return out


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

    # ONE rate resolution for the whole pass. Per-name would be ~180 FRED
    # lookups a day, and worse, would let two names in the same snapshot be
    # priced off different curves -- a cross-sectional feature computed under
    # two conventions is not a cross-section.
    r_simple, r_src = risk_free_simple()
    logger.info("options PIT: r = %.4f (%s)", r_simple, r_src)

    out = {"as_of": as_of, "requested": len(tickers), "stored": 0,
           "already_present": 0, "unavailable": 0, "reasons": {},
           "r_simple": r_simple, "r_source": r_src}
    # Whether the injected builder takes the rate is decided ONCE, by looking
    # at its signature. The first version wrapped the call in `except
    # TypeError` and fell back to a rate-less call -- which would have swallowed
    # any genuine TypeError raised INSIDE build_state and silently re-run the
    # name with a per-name FRED lookup instead. Wrong math gets caught by
    # tests; that would not have.
    import inspect
    try:
        _takes_rate = "r_simple" in inspect.signature(builder).parameters
    except (TypeError, ValueError):                          # pragma: no cover
        _takes_rate = False

    for t in tickers:
        try:
            st = (builder(t, as_of, r_simple=r_simple) if _takes_rate
                  else builder(t, as_of))
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


def _legacy_file_count() -> int:
    """How many option-state files sit at the OLD image path, if any.

    Non-zero here means rows were orphaned by the 2026-08-25 path fix and
    `migrate_legacy()` has not run (or ran on a different container).
    """
    lr = _legacy_root()
    try:
        return len(list(lr.glob("option_state_*.jsonl"))) if lr.exists() else 0
    except OSError:
        return -1


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
                # WHERE it looked. This store spent an hour of 2026-08-25
                # being diagnosed from inference because its health said
                # ABSENT without naming a directory.
                "root": str(r),
                "legacy_root": str(_legacy_root()),
                "legacy_files": _legacy_file_count(),
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
