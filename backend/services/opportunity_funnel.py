"""The market opportunity funnel — look beyond the watchlist, cheaply.

Until now the PM's "radar" ranked Murat's own 34-name watchlist, which answers
"which of the things I already thought of looks best" and never "what did I not
think of". This is the missing stage.

── THE COST DISCIPLINE ─────────────────────────────────────────────────────
Enriching a US equity universe one ticker at a time is 5,000+ serial HTTP
calls, an hour of wall clock, and a rate-limit ban. The funnel therefore
narrows in stages, and each stage is allowed a strictly more expensive kind of
call than the one before it:

    Stage 0  universe        one cached symbol-list call        ~5,000 names
    Stage 1  cheap filter    BATCH price history, ~200/call       ~1,500
    Stage 2  cheap features  arithmetic on data already held        ~250
    Stage 3  deep enrich     per-ticker calls, BOUNDED               ~40
    Stage 4  candidates      the joint optimizer's input             ~25

Only stage 3 is per-ticker, and its size is a hard cap, not a hope.

── THE EVIDENCE DISCIPLINE ─────────────────────────────────────────────────
A funnel is a ranking machine, and this programme has killed most rankings.
Every ordering step here asks `signal_registry` what role a signal is permitted
to play, and the registry refuses on the ones that matter:

  * `momentum_12_1` is CLOSED. Momentum is computed and DISPLAYED because it
    describes a name, and it may not order the funnel.
  * `analyst_target_upside_xs` is CLOSED/PERVERSE — high implied upside was
    a NEGATIVE cross-sectional predictor at t -3.6/-7.2. The PM may use a
    haircut target to SIZE a name chosen on other grounds (RISK_INPUT); the
    funnel may not use it to CHOOSE one. This is the single most important
    constraint in the module, because raw upside is the obvious thing to sort
    by and it is the thing that loses money.
  * `low_volatility` and liquidity are FILTERS, and are used as filters.
  * `profitability_small` is the one permitted PICKER that is computable from
    free data, so it is what actually does the choosing.

Every survivor carries `why`, a list of the specific facts that got it through.
A candidate that cannot say why it is here is a bug, not a suggestion.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "funnel_cache"

# ── stage sizes (hard caps, not targets) ────────────────────────────────────
STAGE1_KEEP = 1500
STAGE2_KEEP = 250
STAGE3_KEEP = 40
STAGE4_KEEP = 25

BATCH_SIZE = 200            # tickers per yfinance batch download
UNIVERSE_TTL_DAYS = 7

#: Exchange codes that carry a real quoted market. Everything else on the
#: Finnhub US list is the OTC tape, where a $10k ticket IS the day's volume.
#: Excluding it is a declared coverage decision, reported in every run.
LISTED_VENUES = frozenset({"XNAS", "XNYS", "ARCX", "BATS", "XASE"})
PRICES_TTL_HOURS = 20

# ── stage 1 eligibility floors ──────────────────────────────────────────────
MIN_PRICE = 3.0             # sub-$3 is where the spread eats the thesis
MAX_PRICE = 2000.0
MIN_MEDIAN_DOLLAR_VOL = 2_000_000.0    # a $500-$10k ticket must not be the tape
MIN_HISTORY_DAYS = 200

#: Retail bar from the mandate: can $500-$10k move without the spread eating
#: the thesis? Anything thinner is not an opportunity for this account.
RETAIL_TICKET_MAX = 10_000.0
MAX_TICKET_SHARE_OF_ADV = 0.01

#: The shortlist is drawn evenly across this many dollar-volume bands. Five is
#: enough to keep mega-caps from crowding out the small-cap sleeve where the
#: one validated picker actually earned its grade, and coarse enough that each
#: band still holds a few hundred names to choose within.
N_SIZE_STRATA = 5


class FunnelError(RuntimeError):
    """The funnel cannot produce a trustworthy candidate list."""


#: Why each stage dropped what it dropped. A funnel that silently returns three
#: names looks the same as one that found three good ones.
STAGE_FAILURES: dict[str, str] = {}


@dataclass
class Candidate:
    ticker: str
    price: Optional[float] = None
    median_dollar_vol: Optional[float] = None
    vol_annual: Optional[float] = None
    mom_12_1: Optional[float] = None          # DISPLAY ONLY — closed as a picker
    quality: Optional[float] = None           # gross profit / assets
    sector: str = ""
    market_cap: Optional[float] = None
    analyst_upside: Optional[float] = None    # RISK_INPUT only, never the rank
    n_analysts: Optional[int] = None
    insider_score: Optional[float] = None     # SUPPORTED/PICKER, all cap bands
    insider_reason: str = ""                  # why it is absent, when it is
    score: Optional[float] = None
    stage: int = 0
    why: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ─────────────────────────────── stage 0 ────────────────────────────────────

def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _read_cache(name: str, ttl_seconds: float) -> Optional[Any]:
    import json
    p = _cache_path(name)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > ttl_seconds:
        logger.info("funnel cache %s is %.1fh old (ttl %.1fh) — refetching",
                    name, age / 3600, ttl_seconds / 3600)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a corrupt cache is not an empty one
        logger.warning("funnel cache %s unreadable (%s) — refetching", name, exc)
        return None


def _write_cache(name: str, payload: Any) -> None:
    import json
    _cache_path(name).write_text(json.dumps(payload), encoding="utf-8")


def universe(*, force: bool = False, extra: list[str] | None = None) -> dict:
    """Stage 0 — the investable US common-stock universe.

    One cached call. Returns the list AND how it was obtained, because a
    universe that quietly fell back to 34 hand-typed names would make every
    downstream count meaningless.
    """
    cached = None if force else _read_cache(
        "universe.json", UNIVERSE_TTL_DAYS * 86400)
    if cached:
        out = dict(cached)
        out["from_cache"] = True
        return out

    from backend.services.pm_catalysts import _finnhub

    rows = _finnhub("stock/symbol", {"exchange": "US"})
    if not rows:
        from backend.services.pm_catalysts import FETCH_FAILURES
        why = FETCH_FAILURES.get("stock/symbol:", "unknown")
        STAGE_FAILURES["stage0"] = f"symbol list unavailable ({why})"
        raise FunnelError(
            f"Stage 0 could not retrieve a universe ({why}). The funnel refuses "
            f"to fall back to the watchlist: a market-wide radar that silently "
            f"becomes a 34-name watchlist radar is the exact failure this "
            f"module was built to end.")

    keep, dropped = [], {"type": 0, "symbol": 0, "venue": 0}
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        typ = (r.get("type") or "").strip()
        # OOTC is the over-the-counter tape: 17,603 of the 30,933 names, and
        # essentially none of them clear the retail liquidity bar two stages
        # later. Excluding them here saves ~90 batch downloads that would
        # produce nothing, and it is a COVERAGE DECISION, recorded as one.
        if (r.get("mic") or "") not in LISTED_VENUES:
            dropped["venue"] += 1
            continue
        if typ not in ("Common Stock", "ADR"):
            dropped["type"] += 1
            continue
        # Warrants, units, preferreds and foreign lines carry suffixes that
        # yfinance either cannot price or prices as something else.
        if not sym or not sym.replace("-", "").isalnum() or "." in sym \
                or len(sym) > 5:
            dropped["symbol"] += 1
            continue
        keep.append(sym)

    keep = sorted(set(keep) | set(x.upper() for x in (extra or [])))
    out = {
        "tickers": keep,
        "n": len(keep),
        "source": "finnhub /stock/symbol?exchange=US",
        "venues": sorted(LISTED_VENUES),
        "coverage_gap": (
            f"{dropped['venue']} OTC/unlisted symbols excluded at stage 0. They "
            f"are not screened at all, so this funnel cannot see an opportunity "
            f"that exists only on the OTC tape."),
        "dropped": dropped,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "from_cache": False,
    }
    _write_cache("universe.json", out)
    return out


# ─────────────────────────────── stage 1 ────────────────────────────────────

def _batch_history(tickers: list[str], *, period: str = "1y") -> dict:
    """BATCH price history. One call per BATCH_SIZE names, never per name."""
    import numpy as np
    import pandas as pd
    import yfinance as yf

    closes: dict[str, Any] = {}
    volumes: dict[str, Any] = {}
    failed_batches = 0
    for i in range(0, len(tickers), BATCH_SIZE):
        chunk = tickers[i:i + BATCH_SIZE]
        try:
            df = yf.download(chunk, period=period, progress=False,
                             auto_adjust=False, threads=True, group_by="column")
        except Exception as exc:  # noqa: BLE001 - a dead batch is recorded
            failed_batches += 1
            logger.warning("funnel stage 1: batch %d-%d failed (%s)",
                           i, i + len(chunk), exc)
            continue
        if df is None or df.empty:
            failed_batches += 1
            continue
        try:
            c = df["Close"] if "Close" in df else None
            v = df["Volume"] if "Volume" in df else None
        except Exception:  # noqa: BLE001
            c = v = None
        if c is None:
            failed_batches += 1
            continue
        if isinstance(c, pd.Series):          # single-ticker shape
            c = c.to_frame(chunk[0])
            v = v.to_frame(chunk[0]) if v is not None else None
        for t in c.columns:
            closes[str(t)] = c[t]
            if v is not None and t in v.columns:
                volumes[str(t)] = v[t]
        logger.info("funnel stage 1: %d/%d fetched", min(i + BATCH_SIZE,
                                                        len(tickers)), len(tickers))
    if failed_batches:
        STAGE_FAILURES["stage1_batches"] = f"{failed_batches} batch(es) failed"
    return {"close": pd.DataFrame(closes), "volume": pd.DataFrame(volumes),
            "failed_batches": failed_batches}


def stage1(tickers: list[str], *, keep: int = STAGE1_KEEP) -> list[Candidate]:
    """Cheap eligibility: priceable, liquid enough for a retail ticket, alive."""
    import numpy as np

    hist = _batch_history(tickers)
    close, volume = hist["close"], hist["volume"]
    if close.empty:
        raise FunnelError(
            "Stage 1 retrieved no price history at all. This is an outage, not "
            "an empty market — refusing to hand back an empty candidate list "
            "that would read as 'no opportunities today'.")

    out: list[Candidate] = []
    for t in close.columns:
        px = close[t].dropna()
        if len(px) < MIN_HISTORY_DAYS:
            continue
        last = float(px.iloc[-1])
        if not math.isfinite(last) or not (MIN_PRICE <= last <= MAX_PRICE):
            continue
        vol_series = volume[t].dropna() if t in volume.columns else None
        if vol_series is None or vol_series.empty:
            continue
        dollar = (px * vol_series.reindex(px.index).fillna(0)).tail(60)
        mdv = float(dollar.median()) if len(dollar) else 0.0
        if not math.isfinite(mdv) or mdv < MIN_MEDIAN_DOLLAR_VOL:
            continue
        # The retail bar, stated as the mandate states it.
        if RETAIL_TICKET_MAX > MAX_TICKET_SHARE_OF_ADV * mdv:
            continue

        rets = px.pct_change().dropna()
        ann_vol = float(rets.std() * np.sqrt(252)) if len(rets) > 60 else None
        mom = None
        if len(px) >= 250:
            mom = float(px.iloc[-21] / px.iloc[-250] - 1.0)

        c = Candidate(ticker=str(t), price=last, median_dollar_vol=mdv,
                      vol_annual=ann_vol, mom_12_1=mom, stage=1)
        c.why.append(f"liquid: median 60d dollar volume ${mdv/1e6:.1f}m, so a "
                     f"${RETAIL_TICKET_MAX:,.0f} ticket is "
                     f"{100*RETAIL_TICKET_MAX/mdv:.2f}% of a day")
        out.append(c)

    out.sort(key=lambda c: -(c.median_dollar_vol or 0))
    logger.info("funnel stage 1: %d of %d priced names pass eligibility",
                len(out), len(close.columns))
    if len(out) <= keep:
        return out

    # NIGHT-10 (RECO-1): this used to be `out[:keep]` — the `keep` most liquid
    # names. Every survivor has ALREADY cleared the hard retail liquidity gate
    # above, so that truncation controlled no risk; it was a pure size filter,
    # and it silently decided what the whole product could ever recommend.
    # Measured consequence: 0 of 25 final candidates fell inside the small-cap
    # band, and the smallest was $3.8bn — while the only SUPPORTED picker in
    # the registry, `profitability_small`, is licensed on the CRSP small
    # segment and its own entry reads "Net-dead in large/mid". The search and
    # the evidence were pointed at disjoint segments of the market.
    #
    # So retain a size-STRATIFIED sample instead: the eligible list is cut into
    # liquidity deciles and each contributes its share. The pool stays the same
    # size, still every name is retail-tradeable, and the small end survives to
    # the stage where a licensed signal can actually be applied to it.
    n_bands = N_SIZE_STRATA
    per = keep // n_bands
    bands: list[list[Candidate]] = [
        out[i * len(out) // n_bands:(i + 1) * len(out) // n_bands]
        for i in range(n_bands)
    ]
    kept: list[Candidate] = []
    for b in bands:
        kept.extend(b[:per])
    # any remainder goes to the most liquid names that were not already taken
    if len(kept) < keep:
        taken = {c.ticker for c in kept}
        kept.extend([c for c in out if c.ticker not in taken][:keep - len(kept)])
    STAGE_FAILURES["stage1_truncated"] = (
        f"{len(out)} names passed eligibility; kept {len(kept)} as a "
        f"{n_bands}-band size-stratified sample rather than the {keep} most "
        f"liquid. Every kept name clears the retail liquidity gate. The "
        f"{len(out) - len(kept)} dropped were never scored.")
    kept.sort(key=lambda c: -(c.median_dollar_vol or 0))
    return kept


# ─────────────────────────────── stage 2 ────────────────────────────────────

def stage2(cands: list[Candidate], *, keep: int = STAGE2_KEEP) -> list[Candidate]:
    """Rank on FILTERS the registry permits. No closed signal orders anything.

    There is deliberately no return-predicting signal in this stage. Everything
    computable from a price series alone — momentum, reversal, 52-week
    proximity — is CLOSED in the registry as a picker. So stage 2 does what the
    evidence actually supports: it prefers names that are liquid and not
    lottery-like, and hands an unopinionated shortlist to the stage that can
    afford a real signal.
    """
    from backend.services import signal_registry as SR

    reg = SR.load()
    # Fail loud if someone later "improves" this by sorting on momentum.
    for closed in ("momentum_12_1", "reversal_dip", "analyst_target_upside_xs"):
        assert not reg.permits(closed, "PICKER"), (
            f"{closed} must never be permitted to pick")

    assert reg.permits("low_volatility", "FILTER")
    w_lowvol = reg.weight("low_volatility")

    scored: list[tuple[float, Candidate]] = []
    vols = [c.vol_annual for c in cands if c.vol_annual is not None]
    if not vols:
        raise FunnelError("Stage 2 has no volatility estimates to filter on")
    import statistics
    med_vol = statistics.median(vols)

    for c in cands:
        # LIQUIDITY IS A GATE, NOT A SCORE. The first version added
        # log10(dollar_volume) to the rank and the funnel returned the S&P 20:
        # NVDA, AAPL, MSFT, AMZN. That is not a bug in the arithmetic, it is
        # size acting as a picker through the back door — and size is not a
        # permitted signal in the registry. A name that clears the retail
        # ticket bar is liquid ENOUGH, and $29bn a day is not more eligible
        # than $30m a day for a $45k account.
        s = 0.0
        c.why.append("cleared the retail liquidity gate")

        # low volatility, as a FILTER at its registry weight (never a picker)
        if c.vol_annual is not None and med_vol > 0:
            rel = c.vol_annual / med_vol
            s += w_lowvol * max(0.0, min(1.0, 2.0 - rel))
            if rel < 1.0:
                c.why.append(f"volatility {100*c.vol_annual:.0f}%/yr, below the "
                             f"universe median {100*med_vol:.0f}% "
                             f"(low_volatility: SUPPORTED/FILTER)")
        c.score = s
        c.stage = 2
        if c.mom_12_1 is not None:
            c.blocked_by.append(
                "momentum_12_1 is CLOSED/REJECTED (net-dead at honest costs) — "
                "shown for description, not used to rank")
        scored.append((s, c))

    # STRATIFY BY SIZE before taking the shortlist. Without this, whatever
    # correlates with size wins the whole funnel, and `profitability_small` —
    # the only PICKER the registry validates, and validated specifically in the
    # SMALL segment — would never be applied to a small-cap name.
    scored.sort(key=lambda kv: -(kv[1].median_dollar_vol or 0))
    n = len(scored)
    strata: list[list[Candidate]] = [[] for _ in range(N_SIZE_STRATA)]
    for i, (_, c) in enumerate(scored):
        strata[min(N_SIZE_STRATA - 1, i * N_SIZE_STRATA // max(1, n))].append(c)

    per = max(1, keep // N_SIZE_STRATA)
    out: list[Candidate] = []
    for band, bucket in enumerate(strata):
        bucket.sort(key=lambda c: -(c.score or 0.0))
        for c in bucket[:per]:
            c.why.append(f"size band {band + 1} of {N_SIZE_STRATA} by dollar "
                         f"volume — the shortlist is stratified so that size "
                         f"cannot act as a picker")
            out.append(c)
    logger.info("funnel stage 2: %d shortlisted across %d size bands",
                len(out), N_SIZE_STRATA)
    return out[:keep]


# ─────────────────────────────── stage 3 ────────────────────────────────────

def stage3(cands: list[Candidate], *, keep: int = STAGE3_KEEP,
           budget: int = STAGE3_KEEP * 3) -> list[Candidate]:
    """Deep enrichment. The ONLY per-ticker stage, and it is hard-capped.

    `budget` is the maximum number of per-ticker calls this stage may make,
    ever. It is not a target and it is not adaptive: if enrichment fails on
    half the names, the stage returns fewer candidates and says so, rather than
    walking further down the list until it has filled a quota.
    """
    from backend.services import pm_engine, signal_registry as SR

    reg = SR.load()
    assert reg.permits("profitability_small", "PICKER"), (
        "profitability_small is the funnel's only permitted picker")
    w_quality = reg.weight("profitability_small")

    enriched: list[Candidate] = []
    calls = 0
    failures = 0
    reasons: dict[str, int] = {}
    # Interleave the stage-2 strata so a budget exhausted early still spans the
    # size range instead of enriching only the largest band.
    cands = _interleave(cands)
    for c in cands:
        if calls >= budget or len(enriched) >= keep:
            break
        calls += 1
        fund, why = _fundamentals(c.ticker)
        if fund is None:
            failures += 1
            reasons[why] = reasons.get(why, 0) + 1
            continue

        c.sector = fund.get("sector") or ""
        c.market_cap = fund.get("market_cap")
        c.quality = fund.get("gross_profitability")
        c.analyst_upside = (None if fund.get("target") is None or not c.price
                            else float(fund["target"]) / c.price - 1.0)
        c.n_analysts = fund.get("n_analysts")

        # `insider_opportunistic` is SUPPORTED/PICKER and — unlike
        # profitability_small — licensed across ALL cap bands, so it is the one
        # signal that can carry evidence on a large-cap candidate. It was worth
        # wiring only after NIGHT-10 fixed the collector: the fetcher read a
        # field the API returns as null, so every ticker scored a confident 0.0.
        calls += 1
        c.insider_score, c.insider_reason = _insider(c.ticker)

        c.stage = 3
        if c.insider_score is not None:
            c.why.append(
                f"opportunistic insider buy score {c.insider_score:.2f} "
                f"(insider_opportunistic: SUPPORTED/PICKER, weight "
                f"{reg.weight('insider_opportunistic')})")
        elif c.insider_reason:
            c.blocked_by.append(
                f"insider_opportunistic UNSCOREABLE ({c.insider_reason}) — "
                f"absent, not zero")
        if c.quality is not None:
            c.why.append(
                f"gross profitability {c.quality:.2f} "
                f"(profitability_small: SUPPORTED/PICKER, weight {w_quality})")
        if c.analyst_upside is not None:
            c.blocked_by.append(
                f"analyst upside {100*c.analyst_upside:+.0f}% recorded as a "
                f"RISK_INPUT for sizing only — analyst_target_upside_xs is "
                f"CLOSED/PERVERSE as a picker (t -3.6 largemid, -7.2 small), "
                f"so it does NOT rank this candidate")
        enriched.append(c)

    if failures:
        detail = ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items()))
        STAGE_FAILURES["stage3"] = (
            f"{failures} of {calls} enrichment call(s) failed ({detail})")
    logger.info("funnel stage 3: %d enriched, %d failed, %d calls (budget %d)",
                len(enriched), failures, calls, budget)
    return enriched


def _insider(ticker: str) -> tuple[Optional[float], str]:
    """Opportunistic open-market buy score, or None AND the reason why not.

    Returning a reason rather than a zero is the whole point: "no insider
    bought" and "the feed carried no SEC transaction codes" are different facts
    and were the same value until NIGHT-10.
    """
    try:
        from backend.services.insider_trading import (
            compute_opportunistic_buy_score, get_insider_transactions,
        )
        s = compute_opportunistic_buy_score(get_insider_transactions(ticker))
    except Exception as exc:  # noqa: BLE001 - the reason IS the result
        return None, f"{type(exc).__name__}: {exc}"
    if s.get("available") is False or s.get("opp_score") is None:
        return None, str(s.get("reason") or "unavailable")
    return float(s["opp_score"]), ""


def _interleave(cands: list[Candidate]) -> list[Candidate]:
    """Round-robin the size bands so any prefix of the list spans the range."""
    bands: dict[str, list[Candidate]] = {}
    for c in cands:
        key = next((w for w in c.why if w.startswith("size band")), "unbanded")
        bands.setdefault(key, []).append(c)
    out: list[Candidate] = []
    order = sorted(bands)
    i = 0
    while len(out) < len(cands):
        added = False
        for k in order:
            if i < len(bands[k]):
                out.append(bands[k][i])
                added = True
        if not added:
            break
        i += 1
    return out


def _fundamentals(ticker: str) -> tuple[Optional[dict], str]:
    """Fundamentals for one name, from the source most likely to answer.

    Finnhub `/stock/metric` is primary and yfinance `.info` is the fallback,
    which is the reverse of what the rest of this repo does. The reason is
    measured, not stylistic: a funnel run issues ~27 batch price downloads
    immediately before this stage, and Yahoo rate-limits the crumb endpoint
    that `.info` needs, so the FIRST run of the funnel reliably fails 100% of
    its enrichment calls. It did, on 2026-08-11, and returned zero candidates —
    correctly, and uselessly.

    Returns (payload, reason). `payload is None` always carries a reason, so a
    name with no fundamentals is never confused with a name that has bad ones.
    """
    from backend.services.pm_catalysts import _finnhub, FETCH_FAILURES

    m = _finnhub("stock/metric", {"symbol": ticker, "metric": "all"})
    metric = (m or {}).get("metric") or {}
    if metric:
        out: dict = {"source": "finnhub"}
        gm = metric.get("grossMarginTTM")
        at = metric.get("assetTurnoverTTM")
        # Novy-Marx gross profitability = gross profit / assets
        #                              = (gross profit / sales) x (sales / assets)
        if isinstance(gm, (int, float)) and isinstance(at, (int, float)):
            out["gross_profitability"] = float(gm) / 100.0 * float(at)
        elif isinstance(metric.get("roaTTM"), (int, float)):
            # A documented DOWNGRADE, not a silent substitute: ROA is a
            # different (post-cost) quantity, so the candidate is tagged.
            out["gross_profitability"] = float(metric["roaTTM"]) / 100.0
            out["quality_proxy"] = "roaTTM (assetTurnover unavailable)"
        prof = _finnhub("stock/profile2", {"symbol": ticker}) or {}
        out["sector"] = prof.get("finnhubIndustry") or ""
        # Finnhub reports marketCapitalization in the company's REPORTING
        # currency, not USD. Multiplying by 1e6 and calling it dollars
        # overstated IBN by 95x (INR), TSM by 28x (TWD) and FMX by 6x (MXN) —
        # a plausible-looking number that silently decides which cap band a
        # name is in, and therefore which signals are licensed to score it.
        # No FX table is wired here, so a non-USD profile is treated as an
        # UNKNOWN cap rather than converted with a guessed rate. Unknown is
        # already handled correctly downstream: `recommendation.in_universe`
        # refuses to apply a size-limited signal to a name whose size it does
        # not know.
        mc = prof.get("marketCapitalization")
        ccy = str(prof.get("currency") or "").upper()
        if not isinstance(mc, (int, float)):
            out["market_cap"] = None
            out["market_cap_note"] = "finnhub returned no market capitalisation"
        elif ccy and ccy != "USD":
            out["market_cap"] = None
            out["market_cap_note"] = (
                f"finnhub reports market cap in {ccy}, not USD, and no FX "
                f"conversion is wired — recorded as unknown rather than "
                f"converted with a guessed rate")
        else:
            out["market_cap"] = float(mc) * 1e6
        rec = _finnhub("stock/price-target", {"symbol": ticker}) or {}
        tm = rec.get("targetMean")
        out["target"] = float(tm) if isinstance(tm, (int, float)) and tm else None
        out["n_analysts"] = None
        if out.get("gross_profitability") is not None:
            return out, "ok"
        return None, "finnhub had no profitability fields"

    fh_why = FETCH_FAILURES.get(f"stock/metric:{ticker}", "finnhub returned nothing")
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:  # noqa: BLE001 - the reason IS the result
        return None, f"{fh_why}; yfinance {type(exc).__name__}"
    if not info:
        return None, f"{fh_why}; yfinance returned nothing"
    gp, ta = info.get("grossProfits"), info.get("totalAssets")
    out = {"source": "yfinance",
           "sector": str(info.get("sector") or ""),
           "market_cap": (float(info["marketCap"])
                          if isinstance(info.get("marketCap"), (int, float))
                          else None),
           "target": (float(info["targetMeanPrice"])
                      if isinstance(info.get("targetMeanPrice"), (int, float))
                      else None),
           "n_analysts": (int(info["numberOfAnalystOpinions"])
                          if isinstance(info.get("numberOfAnalystOpinions"),
                                        (int, float)) else None)}
    if isinstance(gp, (int, float)) and isinstance(ta, (int, float)) and ta:
        out["gross_profitability"] = float(gp) / float(ta)
        return out, "ok"
    return None, f"{fh_why}; yfinance had no gross profit / assets"


# ─────────────────────────────── stage 4 ────────────────────────────────────

def stage4(cands: list[Candidate], *, keep: int = STAGE4_KEEP) -> list[Candidate]:
    """Final ranking on the permitted picker, with the filters as multipliers."""
    from backend.services import signal_registry as SR

    reg = SR.load()
    w_quality = reg.weight("profitability_small")

    have_q = [c for c in cands if c.quality is not None]
    if not have_q:
        STAGE_FAILURES["stage4"] = (
            "no candidate carried a profitability figure — the funnel has no "
            "permitted picker to rank on")
        logger.error("funnel stage 4: nothing to rank on")
        return []

    qs = sorted(c.quality for c in have_q)  # type: ignore[misc]

    def pct(x: float) -> float:
        import bisect
        return bisect.bisect_left(qs, x) / max(1, len(qs) - 1)

    for c in cands:
        base = pct(c.quality) if c.quality is not None else 0.0
        c.score = w_quality * base + 0.5 * (c.score or 0.0)
        c.stage = 4
    ranked = sorted(cands, key=lambda c: -(c.score or 0.0))[:keep]
    for c in ranked:
        c.why.append("survived to the final shortlist and is eligible for the "
                     "joint portfolio optimizer alongside current holdings")
    return ranked


# ─────────────────────────────── the funnel ─────────────────────────────────

def run(*, extra: list[str] | None = None, force_universe: bool = False,
        stage1_keep: int = STAGE1_KEEP, stage2_keep: int = STAGE2_KEEP,
        stage3_keep: int = STAGE3_KEEP, stage4_keep: int = STAGE4_KEEP,
        max_universe: int | None = None) -> dict:
    """Run all five stages and report the funnel, not just its output."""
    STAGE_FAILURES.clear()
    t0 = time.time()

    u = universe(force=force_universe, extra=extra)
    tickers = u["tickers"]
    truncated = False
    if max_universe and len(tickers) > max_universe:
        # Deterministic truncation, and it is REPORTED. An undisclosed cap
        # reads as "we looked at everything".
        tickers = tickers[:max_universe]
        truncated = True

    s1 = stage1(tickers, keep=stage1_keep)
    s2 = stage2(s1, keep=stage2_keep)
    s3 = stage3(s2, keep=stage3_keep)
    s4 = stage4(s3, keep=stage4_keep)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_secs": round(time.time() - t0, 1),
        "universe": {"n": u["n"], "source": u["source"],
                     "from_cache": u.get("from_cache"),
                     "screened": len(tickers),
                     "truncated": truncated,
                     "truncation_note": (
                         f"universe truncated to the first {max_universe} "
                         f"symbols alphabetically — this is a COVERAGE GAP, not "
                         f"a market view" if truncated else None)},
        "stages": {"stage1_eligible": len(s1), "stage2_shortlist": len(s2),
                   "stage3_enriched": len(s3), "stage4_candidates": len(s4)},
        "failures": dict(STAGE_FAILURES),
        "candidates": [c.to_dict() for c in s4],
        "evidence_basis": _evidence_basis(),
    }


def _evidence_basis() -> dict:
    from backend.services import signal_registry as SR
    reg = SR.load()
    return {
        "ranked_by": [s.signal_id for s in reg.by_role("PICKER")
                      if s.signal_id == "profitability_small"],
        "filtered_by": ["low_volatility", "liquidity (retail ticket bar)"],
        "recorded_but_not_ranked_on": [
            "momentum_12_1 (CLOSED/REJECTED)",
            "analyst_target_upside_xs (CLOSED/PERVERSE — RISK_INPUT only)",
        ],
        "why_not_analyst_upside": (
            "Sorting a universe by analyst-implied upside is the obvious move "
            "and it is the one the lab has measured as NEGATIVE: t -3.6 in "
            "large/mid and -7.2 in small. The funnel records it for sizing and "
            "refuses to rank on it."),
    }
