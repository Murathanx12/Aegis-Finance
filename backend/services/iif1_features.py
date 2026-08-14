"""INTERNET-INVESTIGATOR-FWD-1 — the point-in-time feature snapshot.

`investigator_triggers.score_candidate()` consumes six features per security.
Nothing produced them. This module is the missing half: it assembles them at a
frozen decision timestamp, records where every one came from, and writes an
immutable snapshot the runner reads.

WHY A SNAPSHOT AND NOT A FUNCTION CALL
======================================
A forward trial gets point-in-time discipline almost free, but only if it takes
the offer. What we can fetch at 21:00 tonight IS what was knowable at 21:00
tonight — provided the result is frozen and never recomputed. Recomputing these
features next month would silently substitute a corrected earnings calendar, a
restated filing index and a retroactively split-adjusted price series for the
things the model actually saw, and the trial would be graded against inputs it
never had.

So `assemble()` writes `iif1_features/<date>.json` and **refuses to overwrite
it**. The snapshot, not the code, is the point-in-time record.

WHAT EVERY FEATURE CARRIES
==========================
`value`, `status`, `source`, `published_at`, `observed_at`, `fetched_at`.

`status` is the house tri-state, and it is the whole reason this file is careful:

  `OK_DATA`      measured
  `OK_EMPTY`     genuinely nothing there (no filing in the window, no earnings)
  `UNAVAILABLE`  we could not find out

`OK_EMPTY` and `UNAVAILABLE` must never arrive as the same value. "No filing in
two days" is a calm security; "SEC lookup failed" is an unmeasured one, and
scoring the second as calm is how a throttled feed becomes a trigger list of
quiet names. Only `OK_DATA` is passed to the scorer; `UNAVAILABLE` features are
OMITTED, which `score_candidate` already discloses in its reason string rather
than treating as zero.

DECISION TIME IS NEW YORK TIME
==============================
`decision_ts` is resolved in US/Eastern because every boundary that matters —
the close, an 8-K accepted at 16:05, an earnings call after the bell — is a New
York boundary. A filing is treated as public at its SEC **acceptance**
timestamp, not its filing date: a filing accepted at 18:05 was not available to
anyone during that session, and using the date would hand the model information
from the future by up to a day.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd

from backend import config as _config

logger = logging.getLogger(__name__)

TRIAL = "INTERNET-INVESTIGATOR-FWD-1"

#: Tri-state source contract. Identical vocabulary to the tool layer's, on
#: purpose — this is the same discipline one layer earlier.
OK_DATA = "OK_DATA"
OK_EMPTY = "OK_EMPTY"
UNAVAILABLE = "UNAVAILABLE"

SNAPSHOT_DIR = _config.OPTIMUS_LEDGER_DIR / "iif1_features"

#: The market proxy the residual is taken against.
MARKET = "SPY"

#: Trailing window for the residual z-score. 60 sessions is long enough for the
#: dispersion estimate to mean something and short enough that a regime from two
#: years ago is not setting tonight's bar.
RESID_WINDOW = 60
VOLUME_WINDOW = 20

EARNINGS_WITHIN_DAYS = 5
FILING_WITHIN_DAYS = 2

try:                                            # stdlib on 3.9+, but be explicit
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:                                              # pragma: no cover
    NY = timezone(timedelta(hours=-5))


@dataclass(frozen=True)
class FeatureValue:
    """One feature, with everything needed to argue about it later."""
    value: Any
    status: str
    source: str
    observed_at: str
    fetched_at: str
    published_at: str | None = None
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.status == OK_DATA

    def as_dict(self) -> dict:
        return asdict(self)


def resolve_decision_ts(as_of: str | datetime | None = None) -> datetime:
    """The frozen instant the night is taken to know things at, in New York.

    A naive input is interpreted as New York local time rather than UTC —
    guessing UTC for a string a human typed while thinking about the US close
    would shift every boundary by five hours in the direction that leaks.
    """
    if as_of is None:
        return datetime.now(tz=NY)
    if isinstance(as_of, datetime):
        return as_of.astimezone(NY) if as_of.tzinfo else as_of.replace(tzinfo=NY)
    ts = pd.Timestamp(as_of)
    dt = ts.to_pydatetime()
    return dt.astimezone(NY) if dt.tzinfo else dt.replace(tzinfo=NY)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _history_upto(ticker: str, decision_ts: datetime):
    """OHLCV strictly at or before `decision_ts`, or None if unavailable.

    Raises nothing: an unavailable history is a status, not an exception, and
    the caller records which of the two it got.
    """
    from backend.services.data_fetcher import fetch_ticker_history
    df = fetch_ticker_history(ticker, period="1y")
    if df is None or getattr(df, "empty", True):
        return None
    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(NY)
    else:
        idx = idx.tz_convert(NY)
    df = df.copy()
    df.index = idx
    # Strictly at-or-before. A bar dated today is only usable once the session
    # it summarises has ended, and `decision_ts` is what decides that.
    return df[df.index <= decision_ts]


def _price_and_volume(ticker: str, decision_ts: datetime,
                      fetched: str) -> dict[str, FeatureValue]:
    obs = decision_ts.isoformat()
    src = "yfinance:history(1y)"

    def unavailable(note: str) -> dict[str, FeatureValue]:
        return {n: FeatureValue(None, UNAVAILABLE, src, obs, fetched, note=note)
                for n in ("price", "dollar_volume_20d", "volume_z_20d",
                          "abs_resid_return_z_1d")}

    try:
        hist = _history_upto(ticker, decision_ts)
    except Exception as exc:                                   # noqa: BLE001
        return unavailable(f"history fetch failed: {type(exc).__name__}: {exc}")
    if hist is None or hist.empty:
        return unavailable("no price history at or before the decision time")

    close = pd.to_numeric(hist.get("Close"), errors="coerce").dropna()
    vol = pd.to_numeric(hist.get("Volume"), errors="coerce").dropna()
    if close.empty:
        return unavailable("no usable Close series")

    last_bar = close.index[-1]
    published = last_bar.isoformat()
    out: dict[str, FeatureValue] = {}

    out["price"] = FeatureValue(float(close.iloc[-1]), OK_DATA, src, obs,
                                fetched, published_at=published)

    if len(vol) >= VOLUME_WINDOW:
        dv = (close.reindex(vol.index).ffill() * vol).tail(VOLUME_WINDOW)
        out["dollar_volume_20d"] = FeatureValue(
            float(np.nanmedian(dv.values)), OK_DATA, src, obs, fetched,
            published_at=published,
            note="median of close x volume over the last 20 sessions")
        v = vol.tail(VOLUME_WINDOW * 3)
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        if sd > 0:
            out["volume_z_20d"] = FeatureValue(
                float((vol.iloc[-1] - mu) / sd), OK_DATA, src, obs, fetched,
                published_at=published)
        else:
            out["volume_z_20d"] = FeatureValue(
                None, UNAVAILABLE, src, obs, fetched,
                note="zero volume dispersion — a z-score here would be a "
                     "division by zero dressed up as calm")
    else:
        for n in ("dollar_volume_20d", "volume_z_20d"):
            out[n] = FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                                  note=f"fewer than {VOLUME_WINDOW} volume bars")

    out["abs_resid_return_z_1d"] = _resid_z(ticker, close, decision_ts, fetched)
    return out


_MARKET_CACHE: dict[str, Any] = {}


def _market_returns(decision_ts: datetime):
    key = decision_ts.date().isoformat()
    if key not in _MARKET_CACHE:
        try:
            h = _history_upto(MARKET, decision_ts)
            c = pd.to_numeric(h.get("Close"), errors="coerce").dropna() \
                if h is not None and not h.empty else None
            _MARKET_CACHE[key] = None if c is None or c.empty \
                else c.pct_change().dropna()
        except Exception:                                      # noqa: BLE001
            _MARKET_CACHE[key] = None
    return _MARKET_CACHE[key]


def _resid_z(ticker: str, close, decision_ts: datetime,
             fetched: str) -> FeatureValue:
    """|today's market-adjusted move| in trailing standard deviations.

    Market-ADJUSTED rather than raw, because on a day the whole index falls 3%
    every security prints an unusual move and the trigger list becomes a list of
    large caps. What is wanted is a security doing something its market did not.
    """
    obs = decision_ts.isoformat()
    src = f"yfinance:history(1y) residual vs {MARKET}"
    r = close.pct_change().dropna()
    if len(r) < RESID_WINDOW + 2:
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note=f"fewer than {RESID_WINDOW + 2} return bars")

    m = _market_returns(decision_ts)
    if m is None or m.empty:
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note=f"{MARKET} history unavailable — a raw return "
                                 f"substituted here would silently change what "
                                 f"the feature measures")

    joined = pd.concat([r, m], axis=1, join="inner").dropna()
    joined.columns = ["r", "m"]
    if len(joined) < RESID_WINDOW + 2:
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note="too few overlapping sessions with the market")

    win = joined.tail(RESID_WINDOW + 1)
    var = float(win["m"].var(ddof=1))
    beta = float(win["r"].cov(win["m"]) / var) if var > 0 else 1.0
    resid = win["r"] - beta * win["m"]
    today, hist_resid = float(resid.iloc[-1]), resid.iloc[:-1]
    sd = float(hist_resid.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note="zero residual dispersion")
    return FeatureValue(
        float(abs(today) / sd), OK_DATA, src, obs, fetched,
        published_at=win.index[-1].isoformat(),
        note=f"beta {beta:.3f} over {RESID_WINDOW} sessions")


def _earnings_within(ticker: str, decision_ts: datetime,
                     fetched: str) -> FeatureValue:
    """Is a reported earnings date within the window, either side.

    Both directions on purpose: the run-up and the reaction are both unusual
    states, and the trial is about magnitude, which is elevated around both.
    """
    obs = decision_ts.isoformat()
    src = "yfinance:calendar"
    try:
        from backend.services.earnings_intelligence import get_earnings_summary
        summ = get_earnings_summary(ticker)
    except Exception as exc:                                   # noqa: BLE001
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note=f"earnings lookup failed: {type(exc).__name__}")
    if not isinstance(summ, dict):
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note="earnings lookup returned no object")
    if str(summ.get("status", "")).upper() in {"UNAVAILABLE", "ERROR"}:
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note=f"upstream said {summ.get('status')}")

    raw = summ.get("next_earnings_date") or summ.get("last_earnings_date")
    if not raw:
        # Genuinely nothing scheduled that we can see. NOT the same as a failed
        # lookup, and the distinction is the whole point of the tri-state.
        return FeatureValue(False, OK_EMPTY, src, obs, fetched,
                            note="no earnings date reported")
    try:
        d = pd.Timestamp(raw).date()
    except Exception:                                          # noqa: BLE001
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note=f"unparseable earnings date {raw!r}")
    delta = abs((d - decision_ts.date()).days)
    return FeatureValue(bool(delta <= EARNINGS_WITHIN_DAYS), OK_DATA, src, obs,
                        fetched, published_at=str(d),
                        note=f"{delta}d from the decision date")


def _filing_within(ticker: str, decision_ts: datetime,
                   fetched: str) -> FeatureValue:
    """A fresh SEC filing that was PUBLIC at the decision time.

    Acceptance, not filing date. A filing accepted at 18:05 was available to
    nobody during that session; treating it as same-day information hands the
    model up to a day of the future.
    """
    obs = decision_ts.isoformat()
    src = "sec:data.sec.gov/submissions"
    try:
        from backend.services import edgar_events as EE
        cik = EE.lookup_cik(ticker)
        if cik is None:
            return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                                note="no CIK mapping for this ticker")
        sub = EE._fetch_submissions(cik)
    except Exception as exc:                                   # noqa: BLE001
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note=f"EDGAR lookup failed: {type(exc).__name__}")
    if not sub:
        return FeatureValue(None, UNAVAILABLE, src, obs, fetched,
                            note="EDGAR returned no submissions object")

    recent = (sub.get("filings") or {}).get("recent") or {}
    accepted = recent.get("acceptanceDateTime") or []
    filed = recent.get("filingDate") or []
    forms = recent.get("form") or []
    if not forms:
        return FeatureValue(False, OK_EMPTY, src, obs, fetched,
                            note="no recent filings listed")

    cutoff = decision_ts - timedelta(days=FILING_WITHIN_DAYS)
    newest_public: datetime | None = None
    used = "acceptanceDateTime"
    for i in range(len(forms)):
        ts = None
        if i < len(accepted) and accepted[i]:
            try:
                ts = pd.Timestamp(accepted[i]).to_pydatetime()
                ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
                ts = ts.astimezone(NY)
            except Exception:                                  # noqa: BLE001
                ts = None
        if ts is None and i < len(filed) and filed[i]:
            # Fall back to the DATE, and say so. Assuming a time would be
            # inventing precision the source did not give us.
            try:
                d = pd.Timestamp(filed[i]).to_pydatetime().date()
                ts = datetime(d.year, d.month, d.day, 23, 59, tzinfo=NY)
                used = "filingDate (acceptance missing; end-of-day assumed)"
            except Exception:                                  # noqa: BLE001
                ts = None
        if ts is None or ts > decision_ts:
            continue                       # not yet public at the decision time
        if newest_public is None or ts > newest_public:
            newest_public = ts

    if newest_public is None:
        return FeatureValue(False, OK_EMPTY, src, obs, fetched,
                            note="no filing was public at the decision time")
    return FeatureValue(bool(newest_public >= cutoff), OK_DATA, src, obs,
                        fetched, published_at=newest_public.isoformat(),
                        note=f"newest public filing via {used}")


def assemble_ticker(ticker: str, decision_ts: datetime) -> dict[str, FeatureValue]:
    """Every feature for one security, each with its own status."""
    fetched = _now_iso()
    out = _price_and_volume(ticker, decision_ts, fetched)
    out["earnings_within_5d"] = _earnings_within(ticker, decision_ts, fetched)
    out["filing_within_2d"] = _filing_within(ticker, decision_ts, fetched)
    return out


def default_universe() -> list[str]:
    """The screener universe, deduplicated and ordered.

    Deterministic ordering matters: the trigger score breaks ties by ticker, so
    a universe that arrives in a different order must still produce the same
    forty names.
    """
    su = _config.config.get("stock_universe") or {}
    names: set[str] = set(su.get("default_watchlist") or [])
    for lst in (su.get("sector_stocks") or {}).values():
        names.update(lst or [])
    return sorted(names)


def assemble(as_of: str | datetime | None = None,
             universe: Iterable[str] | None = None) -> dict:
    """The night's frozen feature snapshot.

    Returns the runner-shaped `features` dict plus the provenance that makes it
    auditable. Only `OK_DATA` features reach the scorer — an `UNAVAILABLE` one
    is omitted, which `score_candidate` discloses rather than scoring as zero.
    """
    ts = resolve_decision_ts(as_of)
    names = list(universe) if universe is not None else default_universe()

    features: dict[str, dict] = {}
    provenance: dict[str, dict] = {}
    unavailable: dict[str, dict] = {}
    status_counts: dict[str, int] = {OK_DATA: 0, OK_EMPTY: 0, UNAVAILABLE: 0}

    for t in names:
        vals = assemble_ticker(t, ts)
        provenance[t] = {k: v.as_dict() for k, v in vals.items()}
        usable = {k: v.value for k, v in vals.items() if v.usable}
        # OK_EMPTY is a measurement: "no filing" is False, not missing.
        usable.update({k: v.value for k, v in vals.items()
                       if v.status == OK_EMPTY and v.value is not None})
        if usable:
            features[t] = usable
        bad = {k: v.note for k, v in vals.items() if v.status == UNAVAILABLE}
        if bad:
            unavailable[t] = bad
        for v in vals.values():
            status_counts[v.status] = status_counts.get(v.status, 0) + 1

    return {
        "trial": TRIAL,
        "decision_ts": ts.isoformat(),
        "decision_ts_tz": str(ts.tzinfo),
        "assembled_at": _now_iso(),
        "n_universe": len(names),
        "n_with_any_feature": len(features),
        "n_fully_unavailable": len(names) - len(features),
        "status_counts": status_counts,
        "features": features,
        "provenance": provenance,
        "unavailable": unavailable,
    }


def snapshot_path(decision_ts: datetime) -> "object":
    return SNAPSHOT_DIR / f"{decision_ts.date().isoformat()}.json"


def write_snapshot(snap: dict, *, overwrite: bool = False) -> "object":
    """Freeze the snapshot. Refuses to overwrite unless told twice.

    The refusal is the feature. If a night could be re-assembled in place, the
    point-in-time record would become whatever the last run happened to fetch,
    and nothing downstream could tell.
    """
    ts = resolve_decision_ts(snap["decision_ts"])
    p = snapshot_path(ts)
    if p.exists() and not overwrite:
        raise FileExistsError(
            f"{p} already exists. A feature snapshot is the point-in-time "
            f"record for that night and is not rebuilt — rebuilding it would "
            f"substitute today's corrected calendar, filing index and adjusted "
            f"prices for what the model actually saw. Pass overwrite=True only "
            f"if this night never ran.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    return p


def load_snapshot(decision_ts: datetime) -> dict:
    p = snapshot_path(decision_ts)
    if not p.exists():
        raise FileNotFoundError(
            f"no feature snapshot at {p} — assemble one before running the "
            f"night, so the inputs are frozen before any money is spent")
    return json.loads(p.read_text(encoding="utf-8"))
